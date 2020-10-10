# Bayesian Molecular Property Prediction

This repo is a fork of [Chemprop](https://github.com/chemprop/chemprop). We apply a set of Bayesian methods to the Chemprop directed message passing neural network (D-MPNN). The code can be used to assess predictive accuracy, calibration and performance on a downstream molecular search task.

## Methods

The code contains implementations of eight methods, abbreviated as follows:
* **MAP**: classical *maximum a posteriori* training; we find the regularised maximum likelihood solution.
* **GP**: the final layer of the readout FFN is replaced with a GPyTorch variational GP (https://docs.gpytorch.ai/en/v1.2.0/examples/04_Variational_and_Approximate_GPs/SVGP_Regression_CUDA.html). We train the resulting model end-to-end (deep kernel learning).
* **DropR**: MC dropout across readout FFN layers (https://arxiv.org/abs/1506.02142).
* **DropA**: MC dropout over the full D-MPNN.
* **SWAG**: Stochastic Weight Averaging - Gaussian (https://arxiv.org/abs/1902.02476).
* **SGLD**: Stochastic Gradient Langevin Dynamics (https://www.ics.uci.edu/~welling/publications/papers/stoclangevin_v6.pdf).
* **BBP**: Bayes by Backprop (https://arxiv.org/abs/1505.05424). We use 'local reparameterisation' as a variance reduction technique (https://arxiv.org/abs/1506.02557).
* **DUN**: A novel depth uncertainty network which permits inference over both weights and the number of message passing iterations. Our DUN combines Bayes by Backprop with the 'vanilla' DUN proposed by Antoran et al. (https://arxiv.org/abs/2006.08437).

If you're new to Bayesian learning, these are excellent resources (they helped me a lot!):
1. 'The Case for Bayesian Deep Learning' by Andrew Gordon Wilson (https://arxiv.org/abs/2001.10995)
2. The first two chapters of Yarin Gal's PhD thesis (http://mlg.eng.cam.ac.uk/yarin/thesis/thesis.pdf)
3. The first two chapters of the GP book (http://www.gaussianprocess.org/gpml/chapters/RW.pdf)

## A guide to the code

If you're reading the code for the first time, the best place to start is `/chemprop/train/run_training.py`. The `run_training()` function inside this file executes a run of our core experiment, used to assess predictive accuracy and calibration. `run_training()` contains an outer loop over ensemble members and an inner loop over samples. For each sample, the function saves down predictive means and learned aleatoric uncertainty.

`run_training()` calls Bayesian training loop functions. These are housed within the folder `/chemprop/train/bayes_tr/`. Important classes and functions for Bayesian implementations are housed within the folder `/chemprop/bayes/`.

The secondary experiment is molecular search. The main training loop for this experiment is found in the file `/chemprop/train/pdts.py` (containing the `pdts()` function).

We run experiments via scripts inside the `/scripts/` folder. These scripts set hyperparameter values and then call either `run_training()` or `pdts()`. Hyperparameter settings for all our experiments are listed in the file `/scripts/bayesHyp.py`.

## Data

We perform all experiments using the QM9 regression dataset. With limited additional work the code could be adapted to run with any [MoleculeNet](http://moleculenet.ai/) dataset or with ChEMBL. The original Chemprop code has this functionality.

Datasets from MoleculeNet and a 450K subset of ChEMBL from [http://www.bioinf.jku.at/research/lsc/index.html](http://www.bioinf.jku.at/research/lsc/index.html) have been preprocessed and are available in `data.tar.gz`. To uncompress them, run `tar xvzf data.tar.gz`.

## Installation

The easiest way to install the `chemprop` dependencies is via conda. Here are the steps:

1. Install Miniconda from [https://conda.io/miniconda.html](https://conda.io/miniconda.html)
2. `cd /path/to/chemprop`
3. `conda env create -f environment.yml`
4. `conda activate chemprop` (or `source activate chemprop` for older versions of conda)

If you would like to use functions or classes from `chemprop` in your own code, you can install `chemprop` as a pip package as follows:

1. `cd /path/to/chemprop`
2. `pip install -e .`

Then you can use `import chemprop` or `from chemprop import ...` in your other code.

## Logging

`chempropBayes` is setup for logging with [wandb](https://www.wandb.com/). When running on a GPU offline, set `os.environ['WANDB_MODE'] = 'dryrun'`. Generally the code logs loss, validation accuracy and learning rate (to visualise annealing).

## Results

Results for single models (as opposed to model ensembles) are as follows. We report Accuracy (measured by mean rank across QM9 tasks; lower is better), Miscalibration Area (lower is better) and Search Scores (higher is better). We present the mean and standard deviation across 5 runs. MAs are computed with post-hoc *t*-distribution likelihoods and presented X 10<sup>2</sup>. Search Scores equate to the % of the top 1% of molecules discovered after 30 batch additions.


Method | Accuracy (Mean Rank) | Miscalibration Area | Search Score |
| :---: | :---: | :---: | :---: |
MAP | 21,786 | MAE | 0.011 ± 0.000 |
GP | 133,885 | MAE | 2.666 ± 0.006 |
DropR | 1,128 | RMSE | 0.555 ± 0.047 |
DropA | 642 | RMSE | 1.075 ± 0.054 |
SWAG | 4,200 | RMSE | 0.555 ± 0.023 |
SGLD | 9,880 | RMSE | 1.391 ± 0.012 |
BBP | 168 | RMSE | 2.173 ± 0.090 |
DUN | 3,040 | RMSE | 1.486 ± 0.026 |
