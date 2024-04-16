def print_results(results, dumpall):
    for address in results['per_contract_result']:
        result = results['per_contract_result'][address]
        # if result['code_size'] == -1:
        #     code_info = f"max_chunk:{result['max_chunk']}"
        # elif result['code_size'] > 0:
        #     code_info = f"chunks:{result['code_size_chunks']} bytes:{result['code_size']} max:{result['max_chunk']}"
        # else:
        #     code_info = "failed to get contract size"

        print(result['contract_name'])
        print(f"accessed chunks count: {result['num_chunks']}")
        print(f"accessed chunks verkle cost: {result['addr_code_cost']}")
        print(f"storage slots verkle cost diff: {result['addr_storage_difference']}")
        print(f"CALL with value cost diff: {result['call_opcode_with_value_savings']}")
        print(f"address touching opcodes cost diff: {result['address_touching_opcode_cost_difference']}")
        print(f"CREATE2 cost diff: {result['create2_opcode_cost_difference']}")
        if dumpall:
            print(f", all chunks={','.join(map(str, result['chunks'][result['addrress']].keys()))}")
        print("Contract Verkle gas effect = " + str(result['per_contract_diff']))
        print("")
    print("")
    print("Total Verkle gas effect = " + str(results['total_gas_effect']))


def print_storage_access():
    return 0
