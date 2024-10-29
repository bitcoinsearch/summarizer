import sys
import openai
from tqdm import tqdm
from openai.error import APIError, PermissionError, AuthenticationError, InvalidAPIType, ServiceUnavailableError
import time
import traceback
from loguru import logger

from src.config import TOKENIZER, OPENAI_API_KEY, OPENAI_ORG_KEY, CHAT_COMPLETION_MODEL, COMPLETION_MODEL

openai.organization = OPENAI_ORG_KEY
openai.api_key = OPENAI_API_KEY


def generate_summary(prompt):
    summarization_prompt = f"""Suppose you are a programmer and you are enriched by programming knowledge. You will be going through other programmers mail sent to you and you will be extracting all the important information out of the mail and composing a blog post. Even if the mail is divided into parts and parts, your extraction summary should not be in bullet points. It should be in multiple paragraphs. I repeat, never in bullet points. You have to follow some rules while giving a detailed summary. 
    The rules are below:
        1. While extracting, avoid using phrases referring to the context. Instead, directly present the information or points covered.  Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
        2. The summary tone should be formal and full of information.
        3. Add spaces after using punctuation and follow all the grammatical rules.
        4. Any links given within the text should be retained, appropriately incorporated and formatted in markdown as [link text](URL).
        5. The farewell part of the email should be completely ignored.
        6. Ensure that summary is not simply a rephrase of the original content with minor word changes, but a restructured and simplified rendition of the main points.
        7. Most importantly, this extracted information should be relative of the size of the email. If it is a bigger email, the extracted summary can be longer than a very short email.
        8. Break down the summary into concise, meaningful paragraphs ensuring each paragraph captures a unique aspect or perspective from the original text.
        9. Do not refer to cryptocurrency or cryptocurrencies. This is a summary for the Bitcoin community. Substitute all instances of cryptocurrencies with Bitcoin and Lightning as appropriate.
        10. URLs should be formatted in markdown syntax, where the clickable text is placed in square brackets followed by the URL in parentheses, without spaces between them (e.g., [OpenAI](https://www.openai.com)). This format enhances readability and accessibility.
    \n\nCONTEXT:\n\n{prompt}"""
    response = openai.Completion.create(
        model=COMPLETION_MODEL,
        prompt=summarization_prompt,
        temperature=0.7,
        max_tokens=1000,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=1
    )
    response_str = response["choices"][0]["text"].strip()
    return response_str


def consolidate_summary(prompt):
    consolidate_prompt = f"""Suppose you are a programmer and you are enriched by programming knowledge. You have to consolidate below text based on the rules.
    The rules are below:
        1. While extracting, avoid using phrases referring to the context. Instead, directly present the information or points covered.  Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
        2. The summary tone should be formal and full of information.
        3. Add spaces after using punctuation and follow all the grammatical rules.
        4. Any links given within the text should be retained, appropriately incorporated and formatted in markdown as [link text](URL).
        5. The farewell part of the email should be completely ignored.
        6. Ensure that summary is not simply a rephrase of the original content with minor word changes, but a restructured and simplified rendition of the main points.
        7. Most importantly, this extracted information should be relative of the size of the email. If it is a bigger email, the extracted summary can be longer than a very short email. 
        8. Break down the summary into concise, meaningful paragraphs ensuring each paragraph captures a unique aspect or perspective from the original text.
        9. Do not refer to cryptocurrency or cryptocurrencies. This is a summary for the Bitcoin community. Substitute all instances of cryptocurrencies with Bitcoin and Lightning as appropriate.
        10. URLs should be formatted in markdown syntax, where the clickable text is placed in square brackets followed by the URL in parentheses, without spaces between them (e.g., [OpenAI](https://www.openai.com)). This format enhances readability and accessibility.
    \n\nCONTEXT:\n\n{prompt}"""
    response = openai.Completion.create(
        model=COMPLETION_MODEL,
        prompt=consolidate_prompt,
        temperature=0.7,
        max_tokens=1000,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=1
    )
    response_str = response["choices"][0]["text"].strip()
    return response_str


def generate_title(prompt):
    title_generation_prompt = f"Generate an appropriate title for below context.\n\n CONTEXT:\n\n{prompt}"
    response = openai.Completion.create(
        model=COMPLETION_MODEL,
        prompt=title_generation_prompt,
        temperature=0.7,
        max_tokens=30,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=1
    )
    response_str = response["choices"][0]["text"].replace("\n", "").strip()
    return response_str


def generate_chatgpt_summary(body, custom_prompt=None):
    if custom_prompt:
        summarization_prompt = f"""{custom_prompt}\n\nCONTEXT:\n\n{body}"""
    else:
        summarization_prompt = f"""Suppose you are a programmer and you are enriched by programming knowledge. You will be going through other programmers mail sent to you and you will be extracting all the important information out of the mail and composing a blog post. Even if the mail is divided into parts and parts, your extraction summary should not be in bullet points. It should be in multiple paragraphs. I repeat, never in bullet points. You have to follow some rules while giving a detailed summary. 
        The rules are below:
            1. While extracting, avoid using phrases referring to the context. Instead, directly present the information or points covered.  Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
            2. The summary tone should be formal and full of information.
            3. Add spaces after using punctuation and follow all the grammatical rules.
            4. Any links given within the text should be retained, appropriately incorporated and formatted in markdown as [link text](URL).
            5. The farewell part of the email should be completely ignored.
            6. Ensure that the summary is not simply a rephrase of the original content with minor word changes, but a restructured and simplified rendition of the main points.
            7. Most importantly, this extracted information should be relative of the size of the email. If it is a bigger email, the extracted summary can be longer than a very short email.  
            8. Break down the summary into concise, meaningful paragraphs ensuring each paragraph captures a unique aspect or perspective from the original text.
            9. URLs should be formatted in markdown syntax, where the clickable text is placed in square brackets followed by the URL in parentheses, without spaces between them (e.g., [OpenAI](https://www.openai.com)). This format enhances readability and accessibility. 
        \n\nCONTEXT:\n\n{body}"""
    response = openai.ChatCompletion.create(
        model=CHAT_COMPLETION_MODEL,
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
    response_str = response['choices'][0]['message']['content'].strip()
    return response_str


def consolidate_chatgpt_summary(body, custom_prompt=None):
    if custom_prompt:
        consolidate_prompt = f"""{custom_prompt}\n\nCONTEXT:\n\n{body}"""
    else:
        consolidate_prompt = f"""Suppose you are a programmer and you are enriched by programming knowledge. You have to consolidate below text based on the rules.
        The rules are below:
            1. While extracting, avoid using phrases referring to the context. Instead, directly present the information or points covered.  Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..." or "The context questions..." etc
            2. The summary tone should be formal and full of information.
            3. Add spaces after using punctuation and follow all the grammatical rules.
            4. Any links given within the text should be retained, appropriately incorporated and formatted in markdown as [link text](URL).
            5. The farewell part of the email should be completely ignored.
            6. Mention full names (both the first name and last name) of the authors if applicable. If the conversation involves more than two authors, you may use 'et al.' or explicitly list all authors such as 'John Doe, Jane Smith, and three others'.
            7. Ensure that summary is not simply a rephrase of the original content with minor word changes, but a restructured and simplified rendition of the main points.
            8. Most importantly, this extracted information should be relative of the size of the email. If it is a bigger email, the extracted summary can be longer than a very short email. 
            9. Break down the summary into concise, meaningful paragraphs ensuring each paragraph captures a unique aspect or perspective from the original text.
            10. URLs should be formatted in markdown syntax, where the clickable text is placed in square brackets followed by the URL in parentheses, without spaces between them (e.g., [OpenAI](https://www.openai.com)). This format enhances readability and accessibility.
        \n\nCONTEXT:\n\n{body}"""
    response = openai.ChatCompletion.create(
        model=CHAT_COMPLETION_MODEL,
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
    response_str = response['choices'][0]['message']['content'].strip()
    return response_str


def generate_chatgpt_title(prompt):
    title_generation_prompt = f"Generate an appropriate title for below context.\n\n CONTEXT:\n\n{prompt}"
    response = openai.ChatCompletion.create(
        model=CHAT_COMPLETION_MODEL,
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


def create_n_bullets(body_summary, n=3):
    logger.info("creating the bullet points ...")
    bullets_prompt = f"""Summarize the following email into {n} distinct sentences based on the guidelines 
    mentioned below. 
        1. Each sentence you write should not exceed fifteen words. 
        2. Each sentence should begin on a new line and should start with a hyphen (-) and you must add space after hyphen (-).
            E.g., - This is a first sentence. - This is a second sentence. - This is a third sentence.
            E.g., Incorrect: "-This is a sentence.-This is another sentence."
                Correct: "- This is a sentence. - This is another sentence."
        3. Please adhere to all English grammatical rules while writing the sentences, 
            maintaining formal tone and employing proper spacing. 
        4. While summarizing, avoid using phrases referring to the context. Instead, directly present the information or points covered. 
            Do not introduce sentences with phrases like: "The context discusses...", "In this context..." or "The context covers..."
    CONTEXT:\n\n{body_summary}"""

    response = openai.ChatCompletion.create(
        model=CHAT_COMPLETION_MODEL,
        messages=[
            {"role": "system", "content": "You are an intelligent assistant."},
            {"role": "user", "content": f"{bullets_prompt}"},
        ],
        temperature=1,
        max_tokens=300,
    )
    response_str = response['choices'][0]['message']['content'].replace("\n", "").strip()
    response_str = response_str.replace('.- ', '.\n- ')
    response_str = response_str.replace('. - ', '.\n- ')
    return response_str


def split_prompt_into_chunks(prompt, chunk_size):
    tokens = TOKENIZER.encode(prompt)
    chunks = []

    while len(tokens) > 0:
        current_chunk = TOKENIZER.decode(tokens[:chunk_size]).strip()

        if current_chunk:
            chunks.append(current_chunk)

        tokens = tokens[chunk_size:]

    return chunks


def get_summary_chunks(body, tokens_per_sub_body, custom_prompt=None):
    chunks = split_prompt_into_chunks(body, tokens_per_sub_body)
    summaries = []
    # logger.info(f"Total chunks created: {len(chunks)}")

    for chunk in chunks:
        count_gen_sum = 0
        while True:
            try:
                time.sleep(2)
                summary = generate_chatgpt_summary(chunk, custom_prompt)
                summaries.append(summary)
                break
            except (APIError, PermissionError, AuthenticationError, InvalidAPIType, ServiceUnavailableError) as ex:
                logger.error(str(ex))
                count_gen_sum += 1
                time.sleep(0.2)
                if count_gen_sum > 5:
                    sys.exit(f"chunk summary ran into error: {traceback.format_exc()}")

    return summaries


def recursive_summary(body, tokens_per_sub_body, max_length, custom_prompt=None):
    summaries = get_summary_chunks(body, tokens_per_sub_body, custom_prompt)

    summary_length = sum([len(TOKENIZER.encode(s)) for s in summaries])

    logger.info(f"Total tokens of chunk(s) summary: {summary_length} | Max tokens: {max_length}")

    if summary_length > max_length:
        logger.info("entering in recursion ...")
        return recursive_summary("".join(summaries), tokens_per_sub_body, max_length, custom_prompt)
    else:
        return summaries


def gpt_api(body, custom_prompt=None):
    body_length_limit = 127000
    tokens_per_sub_body = 127000
    summaries = recursive_summary(body, tokens_per_sub_body, body_length_limit, custom_prompt)

    if len(summaries) > 1:
        logger.info("generating consolidated summary ...")
        summary_str = "\n".join(summaries)
        count_api = 0
        while True:
            try:
                time.sleep(2)
                consolidated_summaries = consolidate_chatgpt_summary(summary_str, custom_prompt)
                break
            except (APIError, PermissionError, AuthenticationError, InvalidAPIType, ServiceUnavailableError) as ex:
                logger.error(str(ex))
                count_api += 1
                time.sleep(0.2)
                if count_api > 5:
                    sys.exit(f"chunk summary ran into error: {traceback.format_exc()}")

        return consolidated_summaries

    else:
        logger.info("generating individual summary ...")
        return "\n".join(summaries)


def create_summary(body, custom_prompt=None):
    summ = gpt_api(body, custom_prompt)
    return summ


def generate_chatgpt_summary_for_prompt(summarization_prompt, max_tokens):
    response = openai.ChatCompletion.create(
        model=CHAT_COMPLETION_MODEL,
        messages=[
            {"role": "system", "content": "You are an intelligent agent with an exceptional skills in writing."},
            {"role": "user", "content": f"{summarization_prompt}"},
        ],
        temperature=0.7,
        max_tokens=max_tokens
    )
    response_str = response['choices'][0]['message']['content'].strip()
    if response_str.startswith("Summary:"):
        response_str = response_str[8:].strip()
    return response_str


def generate_summary_for_transcript(body, speaker=None):
    transcript_summarization_prompt = f"""As an AI experienced in processing and summarizing complex text, you are tasked with creating an informative blog post from a podcast transcript. 
    Your goal is to condense the material into a coherent narrative that reflects the core ideas and discussions from the transcript in a well-structured format, avoiding bullet points entirely.
    The blog post should be formal, exhibit proper grammatical structure, and contain space after punctuation marks. 
    Summaries should be a true distillation of the original content—not simple rephrasing. 
    Where authors/speakers are mentioned, use their full names or properly apply 'et al.' for pieces involving more than two authors/speakers.
    The length of the summary will depend on the length of the transcript segment. 
    Each paragraph should capture a unique aspect of the discussion, neatly packaging the information into a comprehensive and approachable synthesis for readers.

    Remember to directly integrate information and points without referring to the transcript or source material contextually. 
    Start each paragraph with a clear topic sentence and ensure that the following sentences elaborate on that topic concisely before transitioning smoothly to the next point of discussion. 
    Reflect the significance and narrative of the podcast fully, respecting its original message and intent. 
    Provide a cohesive and insightful blog post summary that enables readers to grasp the essence of the podcast without needing to refer to the full transcript.
    """
    if speaker:
        transcript_summarization_prompt += f"\nSpeaker(s): {speaker}"

    transcript_summarization_prompt += "\nGiven these guidelines, commence the summarization of the provided transcript as follows:"
    transcript_summary = create_summary(body, transcript_summarization_prompt)
    return transcript_summary
