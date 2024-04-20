from typing import Set, Tuple

address = str

WITNESS_BRANCH_COST = 1900
WITNESS_CHUNK_COST = 200
SUBTREE_EDIT_COST = 3000
CHUNK_EDIT_COST = 500
CHUNK_FILL_COST = 6200

VERSION_LEAF_KEY = 0
BALANCE_LEAF_KEY = 1
NONCE_LEAF_KEY = 2
CODE_KECCAK_LEAF_KEY = 3
CODE_SIZE_LEAF_KEY = 4
HEADER_STORAGE_OFFSET = 64
CODE_OFFSET = 128
VERKLE_NODE_WIDTH = 256
MAIN_STORAGE_OFFSET = 256 ** 31

accessed_subtrees: Set[Tuple[address, int]] = {}
accessed_leaves: Set[Tuple[address, int, int]] = {}
edited_subtrees: Set[Tuple[address, int]] = {}
edited_leaves: Set[Tuple[address, int, int]] = {}

total_cost: int = 0


def handle_opcode(opcode: str, addr: address, stack: list[str], mpt_gas: int, mpt_refund: int):
    """
    :param addr: current storage address
    :param opcode: opcode name
    :param stack - current stack
    :param mpt_gas:
    :param mpt_refund:
    :return:
    """
    if opcode == 'SLOAD':
        slot = int(stack[-1])
        (subkey, leafkey) = get_storage_slot_tree_keys(slot)
        access_event(addr, subkey, leafkey)
        #todo: compensate MPT cost
    elif opcode == 'SSTORE':
        slot = int(stack[-1])
        (subkey, leafkey) = get_storage_slot_tree_keys(slot)
        write_event(addr, subkey, leafkey)
        #todo: compensate MPT cost
    elif opcode == 'BALANCE':
        access_event(address, 0, BALANCE_LEAF_KEY)
    elif opcode == 'EXTCODEHASH':
        access_event(address, 0, CODE_KECCAK_LEAF_KEY)
    elif opcode in ['CALL', 'CALLCODE', 'DELEGATECALL', 'STATICCALL']:
        calladdr = stack[-2]
        access_event()
    else:
        "normal opcodes - no changes in gas cost from MPT"
        pass


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


def get_storage_slot_tree_keys(storage_key: int) -> [int, int]:
    if storage_key < (CODE_OFFSET - HEADER_STORAGE_OFFSET):
        pos = HEADER_STORAGE_OFFSET + storage_key
    else:
        pos = MAIN_STORAGE_OFFSET + storage_key
    return (
        pos // 256,
        pos % 256
    )


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


def write_event(addr: address, sub_key: int, leaf_key: int, storage_not_none=False) -> int:
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
