import openai

from src import config

openai.api_key = config.OPENAI_API_KEY


def generate_summary(prompt):
    summarization_prompt = f"""Generate a detailed summary from below email text factually without missing any important information based on the guidelines mentioned below:
    1. While summarizing, avoid using phrases referring to the context. Instead, directly present the information or points covered. 
        Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
    2. Please adhere to all English grammatical rules while writing the sentences, maintaining formal tone and employing proper spacing.
    3. Add a single space after a period (or any punctuation mark) at the end of a sentence before the start of a new sentence.
        E.g., Incorrect: "This is a sentence.This is another sentence." Correct: "This is a sentence. This is another sentence."
    4. Try to retain all the links provided and use them in proper manner at proper place.
    \n\nCONTEXT:\n\n{prompt}"""
    response = openai.Completion.create(
        model=config.COMPLETION_MODEL,
        prompt=summarization_prompt,
        temperature=0.7,
        max_tokens=1000,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=1
    )
    response_str = response["choices"][0]["text"].replace("\n", "").strip()
    return response_str


def consolidate_summary(prompt):
    consolidate_prompt = f"""Consolidate below context based on the guidelines mentioned below. 
    1. While summarizing, avoid using phrases referring to the context. Instead, directly present the information or points covered. 
        Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
    2. Please adhere to all English grammatical rules while writing the sentences, maintaining formal tone and employing proper spacing.
    3. Add a single space after a period (or any punctuation mark) at the end of a sentence before the start of a new sentence.
        E.g., Incorrect: "This is a sentence.This is another sentence." Correct: "This is a sentence. This is another sentence."
    4. Try to retain all the links provided and use them in proper manner at proper place.
    \n\nCONTEXT:\n\n{prompt}"""
    response = openai.Completion.create(
        model=config.COMPLETION_MODEL,
        prompt=consolidate_prompt,
        temperature=0.7,
        max_tokens=1000,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=1
    )
    response_str = response["choices"][0]["text"].replace("\n", "").strip()
    return response_str


def generate_title(prompt):
    title_generation_prompt = f"Generate an appropriate title for below context.\n\n CONTEXT:\n\n{prompt}"
    response = openai.Completion.create(
        model=config.COMPLETION_MODEL,
        prompt=title_generation_prompt,
        temperature=0.7,
        max_tokens=30,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=1
    )
    response_str = response["choices"][0]["text"].replace("\n", "").strip()
    return response_str


def generate_chatgpt_summary(prompt):
    summarization_prompt = f"""Generate a detailed summary from below email text factually without missing any important information based on the guidelines mentioned below:
    1. While summarizing, avoid using phrases referring to the context. Instead, directly present the information or points covered. 
        Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
    2. Please adhere to all English grammatical rules while writing the sentences, maintaining formal tone and employing proper spacing.
    3. Add a single space after a period (or any punctuation mark) at the end of a sentence before the start of a new sentence.
        E.g., Incorrect: "This is a sentence.This is another sentence." Correct: "This is a sentence. This is another sentence."
    4. Try to retain all the links provided and use them in proper manner at proper place.
    \n\nCONTEXT:\n\n{prompt}"""
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are an intelligent assistant."},
            {"role": "user", "content": f"{summarization_prompt}"},
        ],
        temperature=0.7,
        max_tokens=1000,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=1
    )
    response_str = response['choices'][0]['message']['content'].replace("\n", "").strip()
    return response_str


def consolidate_chatgpt_summary(prompt):
    consolidate_prompt = f"""Consolidate below context based on the guidelines mentioned below. 
    1. While summarizing, avoid using phrases referring to the context. Instead, directly present the information or points covered. 
        Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
    2. Please adhere to all English grammatical rules while writing the sentences, maintaining formal tone and employing proper spacing.
    3. Add a single space after a period (or any punctuation mark) at the end of a sentence before the start of a new sentence.
        E.g., Incorrect: "This is a sentence.This is another sentence." Correct: "This is a sentence. This is another sentence."
    4. Try to retain all the links provided and use them in proper manner at proper place.
    \n\nCONTEXT:\n\n{prompt}"""
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are an intelligent assistant."},
            {"role": "user", "content": f"{consolidate_prompt}"},
        ],
        temperature=0.7,
        max_tokens=1000,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=1
    )
    response_str = response['choices'][0]['message']['content'].replace("\n", "").strip()
    return response_str


def generate_chatgpt_title(prompt):
    title_generation_prompt = f"Generate an appropriate title for below context.\n\n CONTEXT:\n\n{prompt}"
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are an intelligent assistant."},
            {"role": "user", "content": f"{title_generation_prompt}"},
        ],
        temperature=0.7,
        max_tokens=1000,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=1
    )
    response_str = response['choices'][0]['message']['content'].replace("\n", "").strip()
    return response_str
