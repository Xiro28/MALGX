import logging
import ollama
import sqlite3
import os

import base64

from src.utils.statistics   import Statistics

class LLMHandler:

    def __init__(self, llm_model: str, system_prompt: str) -> None:

        assert system_prompt is not None, "The system prompt must not be None."
        assert system_prompt is not None, "The system prompt must not be empty."

        self.llm_model = llm_model
        self.system_prompt = system_prompt

        self.conn = sqlite3.connect('cached_prompt.db')
        self.cursor = self.conn.cursor()

        timeout = os.getenv("LGX_OLLAMA_TIMEOUT", 60.0 * 15)


        ollama_url = os.getenv("LGX_OLLAMA_URL", "http://localhost:11434/")
        ollama_api = os.getenv("LGX_OLLAMA_KEY", "")

        if os.getenv("LGX_SKIP_OLLAMA", "false").lower() == "false":

            assert ollama_url != "", "OLLAMA_URL environment variable must be set. Use LGX_OLLAMA_URL to set it."
            
            if ollama_api == "":
                logging.warning("Warning: OLLAMA_KEY environment variable is not set. Use LGX_OLLAMA_KEY to set it for authentication.")

                self.__llm_client = ollama.Client(host=ollama_url, timeout=timeout)
                self.__llm = self.__llm_client.chat
            else:
                logging.info("Using OLLAMA_KEY for authentication.")

                self.__llm_client = ollama.Client(host=ollama_url, timeout=timeout, headers={
                    'Authorization': f'Bearer {ollama_api}'    
                })
                self.__llm = self.__llm_client.chat

            #self.__llm_client.pull(self.llm_model)
            
            response = self.__llm_client.ps()

            for model in response.models:
                logging.info(model.model, model.size, model.size_vram)
        else:
            self.__llm_client = None
            self.__llm = None 

        # create the table if it does not exist
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS prompt_cache (
                prompt TEXT,
                llm_model TEXT,
                configuration TEXT,
                response TEXT,
                token_in INTEGER,
                token_out INTEGER,
                extraction_time INTEGER,
                PRIMARY KEY (prompt, llm_model, configuration)
            )
        ''')

    def __del__(self):
        self.conn.close()

    def __to_llm_dict__(self, role: str, text: str) -> dict:
        return {"role": role, "content": text}
    
    def __to__llm_dict_image__(self, role: str, text: str, image_input: str | bytes) -> dict:
        if not os.path.exists(image_input): # Assuming image_path is a base64 string if the file does not exist
            return {
                "role": role,
                "content": text,
                "images": [image_input]  # base64 string, not a path
            }

        with open(image_input, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        return {
            "role": role,
            "content": text,
            "images": [image_data]  # base64 string, not a path
        }
    
    def invoke_llm_constrained(self, prompt: str, class_response: any, context: any) -> dict | str:
        configuration = {'temperature': 0, "top_p": 0.1}
        grammar = class_response

        # if it's not a user defined grammar, convert the passed class to a grammar 
        if type(class_response) != str:
            grammar = class_response.model_json_schema(mode='serialization')

        if (context != ""):
            _messages = [
                self.__to_llm_dict__("system", f"{self.system_prompt}\n{context}"), 
                self.__to_llm_dict__("user", f"{prompt}"),
            ]
        else:
            _messages = [
                self.__to_llm_dict__("system", f"{self.system_prompt}"), 
                self.__to_llm_dict__("user", f"{prompt}"),
            ]

        self.cursor.execute('SELECT response, token_in, token_out, extraction_time FROM prompt_cache WHERE prompt = ? and llm_model = ? and configuration = ?', (str(_messages), self.llm_model, str(configuration)))
        row = self.cursor.fetchone()

        if row:
            # with open("prompt.txt", "a") as f:
            #     f.writelines(str(_messages))
            #     f.writelines(row[0])

            Statistics.log_llm_call(row[1], row[2])
            Statistics.log_llm_call_duration(row[3])
            try:
                return class_response.model_validate_json(row[0])
            except Exception as e:
                logging.error(e)
                return ""
            
        if self.__llm is None:
            logging.info("LLM calls are skipped. Returning empty string.")
            return ""

        _ret = self.__llm(
            model=self.llm_model,
            messages=_messages,
            stream=False,
            options=configuration
        )

        token_out = _ret["eval_count"]
        token_in = _ret["prompt_eval_count"]
        extraction_time = _ret["total_duration"]

        _ret = _ret["message"]["content"]

  
        try:
            self.cursor.execute('INSERT INTO prompt_cache (prompt, llm_model, configuration, response, token_in, token_out, extraction_time) VALUES (?, ?, ?, ?, ?, ?, ?)', (str(_messages), self.llm_model, str(configuration), _ret, token_in, token_out, extraction_time ))
            self.conn.commit()

            Statistics.log_llm_call(token_in, token_out)
            Statistics.log_llm_call_duration(extraction_time)

            if type(class_response) != str:
                return class_response.model_validate_json(_ret)
            
            return _ret
        except Exception as e:
            logging.error("Errore durante l'inferenza", exc_info=True)
            return None

    def invoke_llm_constrained_image(self, prompt: str, class_response: any, context: any, image_path: str|bytes) -> dict | str:
        configuration = {'temperature': 0, "top_p": 0.1}
        grammar = class_response

        # if it's not a user defined grammar, convert the passed class to a grammar 
        if type(class_response) != str:
            grammar = class_response.model_json_schema(mode='serialization')

        if (context != ""):
            _messages = [
                self.__to_llm_dict__("system", f"{self.system_prompt}\n{context}"), 
                self.__to__llm_dict_image__("user", f"{prompt}", image_path),
            ]
        else:
            _messages = [
                self.__to_llm_dict__("system", f"{self.system_prompt}"), 
                self.__to__llm_dict_image__("user", f"{prompt}", image_path),
            ]

        self.cursor.execute('SELECT response, token_in, token_out, extraction_time FROM prompt_cache WHERE prompt = ? and llm_model = ? and configuration = ?', (str(_messages), self.llm_model, str(configuration)))
        row = self.cursor.fetchone()

        if row:
            # with open("prompt.txt", "a") as f:
            #     f.writelines(str(_messages))
            #     f.writelines(row[0])

            Statistics.log_llm_call(row[1], row[2])
            Statistics.log_llm_call_duration(row[3])
            try:
                return class_response.model_validate_json(row[0])
            except Exception as e:
                logging.error(e)
                return ""
            
        if self.__llm is None:
            logging.info("LLM calls are skipped. Returning empty string.")
            return ""

        _ret = self.__llm(
            model=self.llm_model,
            messages=_messages,
            format=grammar,
            stream=False,
            options=configuration
        )



        token_out = _ret["eval_count"]
        token_in = _ret["prompt_eval_count"]
        extraction_time = _ret["total_duration"]

        _ret = _ret["message"]["content"]

        # print("LLM Response: ", _ret)
  
        try:
            self.cursor.execute('INSERT INTO prompt_cache (prompt, llm_model, configuration, response, token_in, token_out, extraction_time) VALUES (?, ?, ?, ?, ?, ?, ?)', (str(_messages), self.llm_model, str(configuration), _ret, token_in, token_out, extraction_time ))
            self.conn.commit()

            # Statistics.log_llm_call(token_in, token_out)
            # Statistics.log_llm_call_duration(extraction_time)

            if type(class_response) != str:
                return class_response.model_validate_json(_ret)
            
            return _ret
        except Exception as e:
            logging.error("Errore durante l'inferenza", exc_info=True)
            return None
