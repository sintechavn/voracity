def bin_search(target_list: list, num: int):
    left_index = 0
    right_index = len(target_list) - 1
    while left_index <= right_index:
        middle_index = (left_index + right_index) // 2
        middle_value = target_list[middle_index]
        if num < middle_value:
            right_index = middle_index - 1
            continue
        if num > middle_value:
            left_index = middle_index + 1
            continue
        return num
    return False


def bin_search_dict(dict_list: list, num: int, dict_key: str):
    left_index = 0
    right_index = len(dict_list) - 1
    while left_index <= right_index:
        middle_index = (left_index + right_index) // 2
        dict_value = dict_list[middle_index]
        middle_value = dict_value[dict_key]
        if num < middle_value:
            right_index = middle_index - 1
            continue
        if num > middle_value:
            left_index = middle_index + 1
            continue
        return dict_value
    return False
