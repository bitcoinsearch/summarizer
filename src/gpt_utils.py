import openai

from src import config

openai.api_key = config.OPENAI_API_KEY


def generate_summary(prompt):
    summarization_prompt = f"""Suppose you are a programmer and you are enriched by programming knowledge. You will be going through other programmers mail sent to you and you will be extracting all the important information out of the mail and composing a blog post. Even if the mail is divided into parts and parts, your extraction summary should not be in bullet points. It should be in multiple paragraphs. I repeat, never in bullet points. You have to follow some rules while giving a detailed summary. 
    The rules are below:
        1. While extracting, avoid using phrases referring to the context. Instead, directly present the information or points covered.  Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
        2. The summary tone should be formal and full of information.
        3. Add spaces after using punctuation and follow all the grammatical rules.
        4. Try to retain all the links provided and use them in proper manner at proper place.
        5. The farewell part of the email should be completely ignored.
        6. Most importantly, this extracted information should be relative of the size of the email. If it is a bigger email, the extracted summary can be longer than a very short email. 
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
    consolidate_prompt = f"""Suppose you are a programmer and you are enriched by programming knowledge. You have to consolidate below text based on the rules.
    The rules are below:
        1. While extracting, avoid using phrases referring to the context. Instead, directly present the information or points covered.  Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
        2. The summary tone should be formal and full of information.
        3. Add spaces after using punctuation and follow all the grammatical rules.
        4. Try to retain all the links provided and use them in proper manner at proper place.
        5. The farewell part of the email should be completely ignored.
        6. Most importantly, this extracted information should be relative of the size of the email. If it is a bigger email, the extracted summary can be longer than a very short email.
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
    summarization_prompt = f"""Suppose you are a programmer and you are enriched by programming knowledge. You will be going through other programmers mail sent to you and you will be extracting all the important information out of the mail and composing a blog post. Even if the mail is divided into parts and parts, your extraction summary should not be in bullet points. It should be in multiple paragraphs. I repeat, never in bullet points. You have to follow some rules while giving a detailed summary. 
    The rules are below:
        1. While extracting, avoid using phrases referring to the context. Instead, directly present the information or points covered.  Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
        2. The summary tone should be formal and full of information.
        3. Add spaces after using punctuation and follow all the grammatical rules.
        4. Try to retain all the links provided and use them in proper manner at proper place.
        5. The farewell part of the email should be completely ignored.
        6. Most importantly, this extracted information should be relative of the size of the email. If it is a bigger email, the extracted summary can be longer than a very short email. 
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
    consolidate_prompt = f"""Suppose you are a programmer and you are enriched by programming knowledge. You have to consolidate below text based on the rules.
    The rules are below:
        1. While extracting, avoid using phrases referring to the context. Instead, directly present the information or points covered.  Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
        2. The summary tone should be formal and full of information.
        3. Add spaces after using punctuation and follow all the grammatical rules.
        4. Try to retain all the links provided and use them in proper manner at proper place.
        5. The farewell part of the email should be completely ignored.
        6. Most importantly, this extracted information should be relative of the size of the email. If it is a bigger email, the extracted summary can be longer than a very short email.
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
