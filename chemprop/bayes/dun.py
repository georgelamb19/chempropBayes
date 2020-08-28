
import numpy as np
import torch



def neg_log_likeDUN(output, target, sigma, cat):
    """
    function to compute expected loss across different network depths
    inputs:
    - preds_list, list of predictions for different depths
    - targets, single set of targets
    - noise, aleatoric noise (length 12)
    - cat, variational categorical distribution
    """
    
    target_reshape = target.reshape(1,len(target),-1)
    sigma_reshape = sigma.reshape(1, 1, len(sigma))
    
    exponent = -0.5*torch.sum((target_reshape - output)**2/sigma_reshape**2, 2)
    log_coeff = -torch.sum(torch.log(sigma)) - len(sigma) * torch.log(torch.sqrt(torch.tensor(2*np.pi)))
    
    scale = 1 / (exponent.size()[1])
    pre_expectation = - scale * torch.sum(log_coeff + exponent, 1)
    expectation = (pre_expectation * cat).sum()
    
    return expectation
