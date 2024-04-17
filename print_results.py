def print_results(results, dumpall):
    for address in results['per_contract_result']:
        result = results['per_contract_result'][address]

        print(result['contract_name'])
        print(f"contract code size bytes: {result['code_size']}")
        print(f"contract code size chunks: {result['code_size_chunks']}")
        print(f"accessed chunks count: {result['num_chunks']}")
        print(f"accessed chunks verkle cost: {result['addr_code_cost']}")
        print(f"storage slots verkle cost diff: {result['addr_storage_difference']}")
        print(f"storage slots EIP-2200 gas refunds diff*: {result['addr_storage_removed_refund']}")
        print(f"CALL with value cost diff: {result['call_opcode_with_value_diff']}")
        print(f"CREATE2 cost diff: {result['create2_opcode_cost_difference']}")
        if dumpall:
            print(f", all chunks={','.join(map(str, result['chunks'][result['addrress']].keys()))}")
        print("Contract Verkle gas effect = " + str(result['per_contract_diff']))
        print("")
    print(f"address touching opcodes cost diff: {results['address_touching_opcode_cost_difference']}")
    print("")
    print("Total Verkle gas effect = " + str(results['total_gas_effect']))
