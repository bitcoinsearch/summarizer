### Project Setup
1. Install all the dependencies from requirements.txt file: `pip install -r requirements.txt`
2. Set up environment variables: Create `.env` file in the root folder and add following keys -
    `OPENAI_API_KEY="<your_api-Key>"`
3. In `src > config.py` file, set `CHATGPT=True` if you want to generate results using chatgpt model, else set it to `False` and assign `COMPLETION_MODEL` variable with the model's name.
4. Run an app using command: `python app.py`
5. Directories: 
   * `postman_collection`: APIs
   * `previous_results`: results of previous experiments
   * `output`: generate results on api call
   * `notebook`: jupyter-notebook with all the scripts
