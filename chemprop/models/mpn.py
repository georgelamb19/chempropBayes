from typing import List, Union

import numpy as np
from rdkit import Chem
import torch
import torch.nn as nn

from chemprop.args import TrainArgs
from chemprop.features import BatchMolGraph, get_atom_fdim, get_bond_fdim, mol2graph
from chemprop.nn_utils import index_select_ND, get_activation_function
from chemprop.bayes import BayesLinear


class MPNEncoder(nn.Module):
    """A message passing neural network for encoding a molecule."""

    def __init__(self, args: TrainArgs, atom_fdim: int, bond_fdim: int, bbp = False):
        """Initializes the MPNEncoder.

        :param args: Arguments.
        :param atom_fdim: Atom features dimension.
        :param bond_fdim: Bond features dimension.
        :param atom_messages: Whether to use atoms to pass messages instead of bonds.
        """
        super(MPNEncoder, self).__init__()
        self.atom_fdim = atom_fdim
        self.bond_fdim = bond_fdim
        self.atom_messages = args.atom_messages
        self.hidden_size = args.hidden_size
        self.bias = args.bias
        self.depth = args.depth
        self.layers_per_message = 1
        self.undirected = args.undirected
        self.features_only = args.features_only
        self.use_input_features = args.use_input_features
        self.device = args.device
        self.bbp = bbp
        self.prior_sig = args.prior_sig_bbp
        self.dropout_mpnn = args.dropout_mpnn

        if self.features_only:
            return

        # Dropout
        self.dropout_layer = nn.Dropout(p=self.dropout_mpnn)

        # Activation
        self.act_func = get_activation_function(args.activation)

        # Cached zeros
        self.cached_zero_vector = nn.Parameter(torch.zeros(self.hidden_size), requires_grad=False)

        # Input
        input_dim = self.atom_fdim if self.atom_messages else self.bond_fdim

        if self.atom_messages:
            w_h_input_size = self.hidden_size + self.bond_fdim
        else:
            w_h_input_size = self.hidden_size

        # Standard linear layers
        if not self.bbp:
            self.W_i = nn.Linear(input_dim, self.hidden_size, bias=self.bias)
            self.W_h = nn.Linear(w_h_input_size, self.hidden_size, bias=self.bias)
            self.W_o = nn.Linear(self.atom_fdim + self.hidden_size, self.hidden_size)

        
        # BBP linear layers
        else:
            self.W_i = BayesLinear(input_dim, self.hidden_size, self.prior_sig, bias=self.bias)
            self.W_h = BayesLinear(w_h_input_size, self.hidden_size, self.prior_sig, bias=self.bias)
            self.W_o = BayesLinear(self.atom_fdim + self.hidden_size, self.hidden_size, self.prior_sig)



    def forward(self,
                mol_graph: BatchMolGraph,
                features_batch: List[np.ndarray] = None,
                sample = False) -> torch.FloatTensor:
        """
        Encodes a batch of molecular graphs.

        :param mol_graph: A BatchMolGraph representing a batch of molecular graphs.
        :param features_batch: A list of ndarrays containing additional features.
        :return: A PyTorch tensor of shape (num_molecules, hidden_size) containing the encoding of each molecule.
        """
        if self.use_input_features:
            features_batch = torch.from_numpy(np.stack(features_batch)).float().to(self.device)

            if self.features_only:
                return features_batch

        f_atoms, f_bonds, a2b, b2a, b2revb, a_scope, b_scope = mol_graph.get_components(atom_messages=self.atom_messages)
        f_atoms, f_bonds, a2b, b2a, b2revb = f_atoms.to(self.device), f_bonds.to(self.device), a2b.to(self.device), b2a.to(self.device), b2revb.to(self.device)

        if self.atom_messages:
            a2a = mol_graph.get_a2a().to(self.device)

        f_atoms_or_bonds = f_atoms if self.atom_messages else f_bonds
        
        
        
        
        ##### LAYER FOR HIDDEN STATE INITIALISATION #####
        if not self.bbp:
            input = self.W_i(f_atoms_or_bonds)  # num_bonds x hidden_size
        else:
            input, kl = self.W_i(f_atoms_or_bonds, sample)
            tkl = kl
        
        message = self.act_func(input)  # num_bonds x hidden_size
        #################################################
        
        
        
                
        # Message passing
        for depth in range(self.depth - 1):
            if self.undirected:
                message = (message + message[b2revb]) / 2

            if self.atom_messages:
                nei_a_message = index_select_ND(message, a2a)  # num_atoms x max_num_bonds x hidden
                nei_f_bonds = index_select_ND(f_bonds, a2b)  # num_atoms x max_num_bonds x bond_fdim
                nei_message = torch.cat((nei_a_message, nei_f_bonds), dim=2)  # num_atoms x max_num_bonds x hidden + bond_fdim
                message = nei_message.sum(dim=1)  # num_atoms x hidden + bond_fdim
            else:
                # m(a1 -> a2) = [sum_{a0 \in nei(a1)} m(a0 -> a1)] - m(a2 -> a1)
                # message      a_message = sum(nei_a_message)      rev_message
                nei_a_message = index_select_ND(message, a2b)  # num_atoms x max_num_bonds x hidden
                a_message = nei_a_message.sum(dim=1)  # num_atoms x hidden
                rev_message = message[b2revb]  # num_bonds x hidden
                message = a_message[b2a] - rev_message  # num_bonds x hidden



            
            ##### LAYER FOR HIDDEN STATE UPDATES #####
            if not self.bbp:
                message = self.W_h(message)
            else:
                message, kl = self.W_h(message, sample)
                if depth == 0:
                    tkl += kl # ONLY ADD ON KL LOSS ONCE
            
            message = self.act_func(input + message)  # num_bonds x hidden_size
            message = self.dropout_layer(message)  # num_bonds x hidden
            ##########################################
        
        

        
        a2x = a2a if self.atom_messages else a2b
        nei_a_message = index_select_ND(message, a2x)  # num_atoms x max_num_bonds x hidden
        a_message = nei_a_message.sum(dim=1)  # num_atoms x hidden
        a_input = torch.cat([f_atoms, a_message], dim=1)  # num_atoms x (atom_fdim + hidden)
        
        

        
        ##### LAYER FOR ATOM REPRESENTATION #####
        if not self.bbp:
            atom_hiddens = self.W_o(a_input)
        else:
            atom_hiddens, kl = self.W_o(a_input, sample)
            tkl += kl
                
        atom_hiddens = self.act_func(atom_hiddens)  # num_atoms x hidden
        atom_hiddens = self.dropout_layer(atom_hiddens)  # num_atoms x hidden
        #########################################
        
        
        
        
        # Readout
        mol_vecs = []
        for i, (a_start, a_size) in enumerate(a_scope):
            if a_size == 0:
                mol_vecs.append(self.cached_zero_vector)
            else:
                cur_hiddens = atom_hiddens.narrow(0, a_start, a_size)
                mol_vec = cur_hiddens  # (num_atoms, hidden_size)

                mol_vec = mol_vec.sum(dim=0) / a_size
                mol_vecs.append(mol_vec)

        mol_vecs = torch.stack(mol_vecs, dim=0)  # (num_molecules, hidden_size)
        
        if self.use_input_features:
            features_batch = features_batch.to(mol_vecs)
            if len(features_batch.shape) == 1:
                features_batch = features_batch.view([1, features_batch.shape[0]])
            mol_vecs = torch.cat([mol_vecs, features_batch], dim=1)  # (num_molecules, hidden_size)
        
        
        if not self.bbp:
            return mol_vecs  # num_molecules x hidden
        else:
            return mol_vecs, tkl
        
        


class MPN(nn.Module):
    """A message passing neural network for encoding a molecule."""

    def __init__(self,
                 args: TrainArgs,
                 atom_fdim: int = None,
                 bond_fdim: int = None,
                 bbp = False):
        """
        Initializes the MPN.

        :param args: Arguments.
        :param atom_fdim: Atom features dimension.
        :param bond_fdim: Bond features dimension.
        """
        super(MPN, self).__init__()
        self.atom_fdim = atom_fdim or get_atom_fdim()
        self.bond_fdim = bond_fdim or get_bond_fdim(atom_messages=args.atom_messages)
        self.bbp = bbp
        self.encoder = MPNEncoder(args, self.atom_fdim, self.bond_fdim, self.bbp)

    def forward(self,
                batch: Union[List[str], List[Chem.Mol], BatchMolGraph],
                features_batch: List[np.ndarray] = None,
                sample = False) -> torch.FloatTensor:
        """
        Encodes a batch of molecular SMILES strings.

        :param batch: A list of SMILES strings, a list of RDKit molecules, or a BatchMolGraph.
        :param features_batch: A list of ndarrays containing additional features.
        :return: A PyTorch tensor of shape (num_molecules, hidden_size) containing the encoding of each molecule.
        """
        
        if type(batch) != BatchMolGraph:
            batch = mol2graph(batch)

        
        return self.encoder.forward(batch, features_batch, sample)

    
    
    
    
    
    
    
    
    
    
    
    
    
