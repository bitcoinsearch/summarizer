import openai

from src import config

openai.api_key = config.OPENAI_API_KEY


def generate_summary(prompt):
    summarization_prompt = f"Generate a detailed summary from below context fact fully without missing any important information. Do not use the word 'summary' in it.\n\n CONTEXT:\n\n{prompt}"
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
    consolidate_prompt = f"Consolidate below context.\n\n CONTEXT:\n\n{prompt}"
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
    summarization_prompt = f"Generate a detailed summary from below context fact fully without missing any important " \
                           f"information. Try to retain all the links provided and use them in proper manner at " \
                           f"proper place. Do not use the word 'summary' in it. Make the summary in paragraphs and " \
                           f"Use line breaks like `\n` in between new paragraphs. Make this a must to do when you create more paragraphs." \
                           f"use line breaks at proper places. Use cohesive writing style. \n\n CONTEXT:\n\n{prompt}"
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
    1. Please adhere to all English grammatical rules while writing the sentences, maintaining formal tone and employing proper spacing. 
    2. While summarizing, avoid using phrases referring to the context. Instead, directly present the information or points covered. 
    Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers...".
    3. Use line breaks like "\n" in between new paragraphs. Make this a must to do when you create more paragraphs.
    \n\n CONTEXT:\n\n{prompt}"""
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
