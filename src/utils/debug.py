import json

class Debug:
    current_problem : str = ""
    data : dict = {}
    id   : int  = 0


    @staticmethod
    def setProblemToDebug(problem_name: str):
        Debug.current_problem = problem_name

        if problem_name is not Debug.data:
            Debug.data[Debug.current_problem] = list()

    @staticmethod
    def logResult(prompt: str, response: str):
        Debug.data[Debug.current_problem].append((Debug.id, prompt, response))
        Debug.id = Debug.id + 1

    @staticmethod
    def reset():
        pass

    @staticmethod
    def storeResult(path: str):
        return
        with open(path, "w", encoding='utf-8') as f:
            json.dump(Debug.data, f, indent=4)
