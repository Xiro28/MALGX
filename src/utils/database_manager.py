import json

def create_dataset_from_problems(filename: str, problems: set[str], samples: int) -> list[dict]:
    """
    Create a dataset filtered by the given problem names.

    Args:
        problems (set[str]): A set of problem names to filter the dataset.

    Returns:
        list[dict]: A list of dataset entries matching the specified problem names.
    """
    _dataset = get_dataset(filename, samples)
    return [obj for obj in _dataset if obj is not None and obj["problem_name"] in problems]


def get_dataset(filename: str, samples: int) -> list[dict]:
    """
    Load the entire dataset from the JSON file.

    Returns:
        list[dict]: The complete dataset.
    """
    dataset = json.load(open(filename, "r"))

    if samples <= 0:
        return dataset

    _new_dataset = []
    current_problem_name = "None"
    current_count = 0

    for obj in dataset:
        # Check if we have switched to a new problem group
        if obj["problem_name"] != current_problem_name:
            current_problem_name = obj["problem_name"]
            current_count = 0 # Reset the counter for the new group

        # If we are under the limit, add the object and increment
        if current_count < samples:
            _new_dataset.append(obj)
            current_count += 1
        # If we reached the limit, append None
        #else:
        #    _new_dataset.append(None)
            
    return _new_dataset