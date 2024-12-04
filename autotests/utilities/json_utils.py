import json


def save_to_json(data, file_path):
    with open(file_path, 'w') as json_file:
        json.dump(data, json_file, indent=4)


def compare_json_left_in_right(json1, json2, key='', path=''):
    """
    Compares whether all key-value pairs from `json1` exist in `json2`. Extra keys in `json1` are ignored.

    :param json1: The reference dictionary.
    :param json2: The dictionary being compared.
    :param key: The root key name.
    :param path: The path to the key where a value mismatch occurred.
    :return: A dictionary with mismatches in the format:
             {
                 "key_with_difference": {
                     "expected": value_from_json1,
                     "actual": value_from_json2,
                     "path": full_path_to_the_key
                 }
             }, or an empty dictionary if no mismatches are found.
    """
    diff_dict = {}
    if isinstance(json1, dict) and isinstance(json2, dict):
        for key in json1:
            if key not in json2:
                diff_dict[key] = {"expected": json1[key], "actual": "key undefined", "path": f"{path}{key}"}
                continue
            diff_dict.update(compare_json_left_in_right(json1[key], json2[key], key, f"{path}{key}:"))
    elif json1 != json2:
        diff_dict[key] = {"expected": json1, "actual": json2, "path": path[:-1]}
    return diff_dict
