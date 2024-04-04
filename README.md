# Verkle Gas Estimator

Attempt to estimate the gas cost of a transaction, as if it was executed after verkle tree integration.

Verkle trees gas cost are different.
Specifically, accessing CODE is no longer a constant value, but depend on the size of the accessed contract

TODO: This script is WIP. 
Currently, doesn't do actual gas estimation, only counts "Verkle-slots" (31-bytes of code)
