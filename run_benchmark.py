import os
import json
import logging
import argparse

from tqdm       import tqdm
from pathlib    import Path
from itertools  import groupby
from typing     import Literal

from src.lgx     import LGX

from src.core.predicate.condition_cache     import ConditionCache

from src.utils.statistics                   import Statistics
from src.utils.database_manager             import get_dataset

class BenchmarkRunner:
    def __init__(self, test_name:str, model: str, conditional: bool, condition_cache_mode: Literal["full", "non_monotone", "off"], application_file_path: str, dataset_path: str, samples: int):
        self.mode = "json"
        self.model = model
        self.conditional = conditional
        self.use_condition_cache = condition_cache_mode != "off"

        self.samples = samples
        self.dataset_path = dataset_path
        self.application_file = application_file_path
        
        self.output_file = self._generate_output_path(test_name, model)
        self.lgx = LGX("./behaviour/behaviour.lgx.yml", self.application_file, self.model)

        self.statistics = {}

        if not self.use_condition_cache:
            ConditionCache.disable()
        else:
            ConditionCache.enable()
        
        if condition_cache_mode == "non_monotone":
            ConditionCache.set_only_non_monotone()
        elif condition_cache_mode == "full":
            ConditionCache.set_all()


    def _generate_output_path(self, test_name: str, model: str) -> str:
        model_suffix = model.replace(":", "_")
        return f"experiment_results/{model_suffix}/{test_name}.json"


    def run(self):
        dataset = get_dataset(self.dataset_path, samples=self.samples)
        dataset.sort(key=lambda x: x["problem_name"])

        for problem_name, group in groupby(
            dataset, key=lambda x: x["problem_name"]
        ):
            items = list(group)
            results = []

            last_stats = Statistics.get_stats()

            for item in tqdm(
                items, desc=f"Processing {problem_name}", leave=False
            ):
                try:
                    res = self.lgx.infer(item["text"], self.mode)
                    results.append(res.run_asp().inferred_preds)

                except Exception:
                    logging.error(
                        f"Errore inferenza su {problem_name}", exc_info=True
                    )
                    results.append("TIMEOUT")

                self.lgx.clean()

            self.statistics[problem_name] = {
                "results": results,
                **Statistics.get_statistics_since(last_stats)
            }

        self.statistics["dataset"] = self.dataset_path
        self._save_results()

    def _save_results(self):
        path = Path(self.output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding='utf-8') as f:
            json.dump(self.statistics, f, indent=4)

def lgx_runner(test_name: str, model: str, samples: int, dataset: str, application_file: str, cache: bool = True, cache_non_monotone_only: bool = False, conditional: bool = False):
    
    cache_mode = "off"
    if cache:
        cache_mode = "non_monotone" if cache_non_monotone_only else "full"

    BenchmarkRunner(        
        test_name, model, 
        conditional, cache_mode, application_file, 
        dataset, samples
    ).run()

def benchmark_run(model: str, n_samples: int):
    for dataset, test_name, path in zip(["./datasets/dataset_final_lnrs.json", "./datasets/dataset_graph.json"], ["lnrs", "graph"], ["LNRS", "G"]):
        
        lgx_runner(f"{test_name}_llmasp_base",        model=model, samples=n_samples, dataset=dataset, application_file=f"./applications/{path}/llmasp-via-lgx-base.yml", cache=False)
        lgx_runner(f"{test_name}_llmasp_g",           model=model, samples=n_samples, dataset=dataset,  application_file=f"./applications/{path}/llmasp-via-lgx-guard.yml", cache=False)
        lgx_runner(f"{test_name}_lgx_base_no_cache", model=model, samples=n_samples, dataset=dataset, application_file=f"./applications/{path}/lgx.yml", cache=False)
        lgx_runner(f"{test_name}_lgx_base_cache_non_monotone", model=model, samples=n_samples, dataset=dataset, application_file=f"./applications/{path}/lgx.yml", cache_non_monotone_only=True, cache=True)
        lgx_runner(f"{test_name}_lgx_base_cache_adv", model=model, samples=n_samples, dataset=dataset, application_file=f"./applications/{path}/lgx.yml", cache=True)


# Model available: llama3.1:8b, llama3.1:70b, gpt-oss:120b
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run LGX Benchmarks", 
    epilog = """Usage: python run_benchmark.py --model <model_name> [--samples <number_of_samples>] [--help]
                Environment variables:
                LGX_OLLAMA_URL: URL of the Ollama instance to use for the benchmark.
                Example: LGX_OLLAMA_URL=http://url:11434
                    
                LGX_OLLAMA_KEY: API key for authenticating with the Ollama instance.
                Example: LGX_OLLAMA_KEY=sk-ollama-xxxx-xxxx-xxxx

                LGX_OLLAMA_TIMEOUT: Timeout in seconds for each LLM call (default: 900 seconds -> 15 minutes)
                """)
    
    parser.add_argument("--samples", type=int, default=-1, help="Number of samples to run for each test (default: -1 for all)")
    parser.add_argument("--model", type=str, help="Model to use for benchmarking")
    parser.add_argument("--skip_ollama", action='store_true', help="Flag used to skip Ollama calls (It runs only the instances inside the cached_prompt.db)")
    args = parser.parse_args()

    if args.model is None:
        print("Please specify a model using --model")
        exit(1)

    if args.skip_ollama:
        os.environ["LGX_SKIP_OLLAMA"] = "true"
        logging.info("Skipping Ollama calls. Only cached results will be used.")
    else:
        os.environ["LGX_SKIP_OLLAMA"] = "false"
        logging.info("Ollama calls will be made for uncached prompts.")
        

    benchmark_run(args.model, args.samples)

    logging.info("Benchmarking completed.")
