def print_results(results, dumpall):
    for address in results['per_contract_result']:
        result = results['per_contract_result'][address]
        if result['code_size'] == -1:
            code_info = f"max_chunk:{result['max_chunk']}"
        elif result['code_size'] > 0:
            code_info = f"chunks:{result['code_size_chunks']} bytes:{result['code_size']} max:{result['max_chunk']}"
        else:
            code_info = "failed to get contract size"

        print(result['contract_name'])
        print('Code Access Details:')
        print(f"accessed chunks: {result['num_chunks']}")
        print(code_info)
        print(f"accessed chunks verkle cost: {result['addr_code_cost']}")
        print('Storage Access Details:')
        print(f"storage slots reads: {result['addr_storage_reads']}")
        print(f"storage slots edits: {result['addr_storage_edits']}")
        print(f"storage slots fills: {result['addr_storage_fills']}")
        print(f"storage slots verkle cost: {result['addr_storage_cost']}")
        print(f"storage slots verkle savings: {result['addr_storage_savings']}")
        print('Address Touching Opcodes:')
        print(f"CALL with value: {result['call_opcode_with_value_count']}")
        print(f"Others: {result['address_touching_opcode_count']}")
        print('CREATE2 Opcode:')
        print(f"bytes written:{result['create2_opcode_bytes_written']}")
        if dumpall:
            print(f", all={','.join(map(str, result['chunks'][result['addrress']].keys()))}")
    print("Total Verkle gas effect = " + str(results['total_gas_effect']))
