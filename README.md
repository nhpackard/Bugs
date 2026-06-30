# Bugs

This repo contains a recent version of an artificial life model originally reported in
```
Packard, Norman H. "Intrinsic adaptation in a simple model for evolution."
In Artificial life, pp. 141-155. Routledge, 2019.
```
The model has a 2d world containing sensori-motor agents (bugs).  The world has a 2d food field, with which the agents interact by eating. Each agent can sense the food field by looking at sites in its Moore neighborhood.  The continuous food field values are thresholded to obtain one bit per neighboring cell, and these bits are accumulated into an address to access a look-up-table (LUT), so 9 bits.  The output of the LUT is a movement vector that determines the agent's new position for the next time step.  The LUT (in combination with the thresholding) comprise the agent's brain.  If the agent obtains enough food, it reproduces, and its LUT is duplicated with the possibilityt of mutation.  A non-zero mutation rate causes the population of bugs to evolve.

The current implementation explores co-evolution of the LUT (genes) and the sensory apparatus containing the thresholds for each neighborhood cell.

The current research goal is to discover the relationship between energy (food) flux and evolution of successful bugs.

## Implementation

The current implementation has a C layer for fast update of agents' state and the food field, and a python layer for display and control.

