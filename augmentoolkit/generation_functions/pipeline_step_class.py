import json
import logging
import os
import re
import traceback
from augmentoolkit.generation_functions.generation_step_class import GenerationStep
from augmentoolkit.utils.make_id import make_id
from augmentoolkit.utils.write_output_to_file import write_output_to_file


class PipelineStep:
    def __init__(
        self, 
        prompt_path=None,
        default_prompt_folder=None,
        sampling_params=None,
        output_dir=None,
        output_subdir=None,
        save_path=None,
        output_processor=lambda x: x,
        completion_mode=False,
        use_stop=True,
        logging_level=logging.INFO,
        prompt_folder=None,
        intermediate_output_path=None,
        result_key="placeholder_result_key", # this is the key that the result will be saved under in the output dictionary.
        regex=re.compile(r".*", re.DOTALL),
        validation_function=lambda x, y: True,
        max_retries=3,
        **kwargs,
        ): # things that are args here are things that would be in the code. Some of these will be live-tweakable.
        self.prompt_path = prompt_path + ".yaml" if not completion_mode else prompt_path + ".txt"
        self.sampling_params = sampling_params
        self.save_path = save_path
        self.output_processor = output_processor
        self.completion_mode = completion_mode
        self.default_prompt_folder = default_prompt_folder
        self.logging_level = logging_level
        self.use_stop = use_stop
        self.prompt_folder = prompt_folder
        self.intermediate_output_path = intermediate_output_path
        self.result_key = result_key
        self.regex = regex
        self.output_subdir = output_subdir
        self.full_output_path = os.path.join(output_dir, self. output_subdir)
        self.intermediate_output_path_full = os.path.join(self.full_output_path, self.intermediate_output_path)
        self.save_path_dir = os.path.join(self.full_output_path, self.save_path)
        self.validation_function = validation_function
        self.max_retries=max_retries
        self.static_arguments = kwargs # any additional arguments are passed in during generation time. Fits the role of stuff read from the config, like special instructions.
    
    def process_input_data(self, input_data):
        return input_data # this should be a dictionary with the keys being the same as the interpolation spots in the prompt. This function in particular will basically always be overridden in subclasses.
    
    def make_save_path_file(self, idx):
        path = os.path.join(self.full_output_path, self.save_path, f"{str(idx)}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path
    
    def read_previous_output(self, idx, output_list):
        save_path_file = self.make_save_path_file(idx)
        if os.path.exists(save_path_file):
            try:
                # First try UTF-8
                with open(save_path_file, "r", encoding='utf-8') as f:
                    output_data = json.load(f)
                    output_list.append(output_data)
                    return True
            except UnicodeDecodeError:
                # If UTF-8 fails, try with 'utf-8-sig' to handle BOM
                try:
                    with open(save_path_file, "r", encoding='utf-8-sig') as f:
                        output_data = json.load(f)
                        output_list.append(output_data)
                        return True
                except UnicodeDecodeError:
                    # If that fails too, try with errors='replace'
                    try:
                        with open(save_path_file, "r", encoding='utf-8', errors='replace') as f:
                            output_data = json.load(f)
                            output_list.append(output_data)
                            return True
                    except Exception as e:
                        print(f"Error reading file {save_path_file}: {str(e)}")
                        return False
            except Exception as e:
                print(f"Error reading file {save_path_file}: {str(e)}")
                return False
        return False

    
    async def generate_data(self, processed_data, engine_wrapper):
        try:
                
            generator = GenerationStep(
                prompt_path=self.prompt_path,
                default_prompt_folder=self.default_prompt_folder,
                sampling_params=self.sampling_params,
                completion_mode=self.completion_mode,
                engine_wrapper=engine_wrapper,
                output_processor=self.output_processor,
                retries=1, 
                logging_level=self.logging_level,
                use_stop=self.use_stop,
                prompt_folder=self.prompt_folder,
                regex=self.regex,
            )
            
            # print(processed_data)
            
            result, full_output = await generator.generate(**processed_data, **self.static_arguments)
            
            return result, full_output
        except Exception as e:
            print(e)
            traceback.print_exc()
    
    
    
    def save(self, result=None,
    full_output=None,
    idx=None,
    output_list=None,
    input_data=None,):
        id = make_id()
        save_path_file = self.make_save_path_file(idx)
        
        output_data = input_data
        output_data[self.result_key] = result
        write_output_to_file(full_output, self.intermediate_output_path_full, id)
        
        os.makedirs(self.save_path, exist_ok=True)
        with open(save_path_file, "w", encoding='utf-8') as f:
            f.write(json.dumps(output_data, ensure_ascii=False))
        
        output_list.append(output_data)
        return output_data
    
    async def run(self, idx=None,
    input_data=None,
    engine_wrapper=None,
    output_list=None,
      ): # things that are args here are produced during inference time. Including config settings.
        
        read_previous_item = self.read_previous_output(idx, output_list)
        if read_previous_item:
            return
        
        processed_data = self.process_input_data(input_data)
        
        complete = False
        max_retries = self.max_retries
        while not complete and max_retries > 0:
            try:
                result, full_output = await self.generate_data(processed_data, engine_wrapper)
                if self.validation_function(result, input_data):
                    complete = True
            except Exception as e:
                print(e)
                traceback.print_exc() 
            max_retries -= 1
        if not complete: # consider raising here and catching in the actual pipeline.
            return
        
        return self.save(result=result, full_output=full_output, idx=idx, output_list=output_list, input_data=input_data)
        

        