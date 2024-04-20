from typing import Set, Tuple
address = str

WITNESS_BRANCH_COST = 1900
WITNESS_CHUNK_COST = 200
SUBTREE_EDIT_COST = 3000
CHUNK_EDIT_COST = 500
CHUNK_FILL_COST = 6200

accessed_subtrees: Set[Tuple[address, int]] = {}
accessed_leaves: Set[Tuple[address, int, int]] = {}
edited_subtrees: Set[Tuple[address, int]] = {}
edited_leaves: Set[Tuple[address, int, int]] = {}

total_cost: int = 0


def reset_transaction():
    """
    reset all values before each transaction
    :return:
    """
    global total_cost
    total_cost = 0
    accessed_subtrees.clear()
    accessed_leaves.clear()
    edited_subtrees.clear()
    edited_leaves.clear()


def access_event(addr: address, sub_key: int, leaf_key: int):
    """
    If (address, sub_key) is not in accessed_subtrees, charge WITNESS_BRANCH_COST gas and add that tuple to accessed_subtrees.
    If leaf_key is not None and (address, sub_key, leaf_key) is not in accessed_leaves, charge WITNESS_CHUNK_COST gas and add it to accessed_leaves
    """
    global total_cost
    if (addr, sub_key) not in accessed_subtrees:
        new_costs = WITNESS_BRANCH_COST
        accessed_subtrees.add((addr, sub_key))
    if (addr, sub_key, leaf_key) not in accessed_leaves:
        new_costs += WITNESS_CHUNK_COST
        accessed_leaves.add((addr, sub_key, leaf_key))
    total_cost += new_costs


def write_event(addr: address, sub_key: int, leaf_key: int, storage_not_none = False) -> int:
    """
        When a write event of (address, sub_key, leaf_key) occurs, perform the following checks:

        If (address, sub_key) is not in edited_subtrees, charge SUBTREE_EDIT_COST gas and add that tuple to edited_subtrees.
        If leaf_key is not None and (address, sub_key, leaf_key) is not in edited_leaves, charge CHUNK_EDIT_COST gas and add it to edited_leaves
        Additionally, if there was no value stored at (address, sub_key, leaf_key) (ie. the state held None at that position), charge CHUNK_FILL_COST
    """
    global total_cost
    new_costs = 0
    if (addr, sub_key) not in edited_subtrees:
        new_costs += SUBTREE_EDIT_COST
        edited_subtrees.add((addr, sub_key))
    if (addr, sub_key, leaf_key) not in edited_leaves:
        new_costs += CHUNK_EDIT_COST
        edited_leaves.add((addr, sub_key, leaf_key))
    # if leaf_key is None:
    if storage_not_none:
        new_costs += CHUNK_FILL_COST
    total_cost += new_costs
