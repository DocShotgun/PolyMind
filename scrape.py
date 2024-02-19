from bs4 import BeautifulSoup
from urllib.request import Request, urlopen
from curl_cffi import requests
import Shared_vars
from PyPDF2 import PdfReader
import io
if Shared_vars.config.compat:
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(Shared_vars.config.tokenmodel)
from trafilatura import fetch_url, extract
API_ENDPOINT_URI = Shared_vars.API_ENDPOINT_URI

if Shared_vars.TABBY:
    API_ENDPOINT_URI += "v1/completions"
else:
    API_ENDPOINT_URI += "completion"


def get_pdf_from_url(url):
    """
    :param url: url to get pdf file
    :return: PdfReader object
    """
    remote_file = urlopen(Request(url)).read()
    memory_file = io.BytesIO(remote_file)
    pdf_file = PdfReader(memory_file)
    return pdf_file


def tokenize(input):
    if Shared_vars.config.compat:
        encoded_input = tokenizer.encode(input, return_tensors=None)
        return len(encoded_input), encoded_input
    else:
        payload = {
            "add_bos_token": "true",
            "encode_special_tokens": "true",
            "decode_special_tokens": "true",
            "text": input,
            "content": input,
        }
        request = requests.post(
            API_ENDPOINT_URI.replace("completions", "token/encode") if Shared_vars.TABBY else API_ENDPOINT_URI.replace("completion", "tokenize"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {Shared_vars.API_KEY}",
            },
            json=payload,
            timeout=360,
        )
        return request.json()["length"] if Shared_vars.TABBY else len(request.json()["tokens"]), request.json()["tokens"]


def decode(input):
    if Shared_vars.config.compat:
        print(input)
        decoded_text = tokenizer.decode(input, skip_special_tokens=True)
        return decoded_text
    else:
        payload = {
            "add_bos_token": "false",
            "encode_special_tokens": "false",
            "decode_special_tokens": "false",
            "tokens": input,
        }
        request = requests.post(
            API_ENDPOINT_URI.replace("completions", "token/decode") if Shared_vars.TABBY else API_ENDPOINT_URI.replace("completion", "detokenize"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {Shared_vars.API_KEY}",
            },
            json=payload,
            timeout=360,
        )
        return request.json()["text"] if Shared_vars.TABBY else request.json()["content"]


def shorten_text(text, max_tokens):
    currlen, tokens = tokenize(text)
    if currlen < max_tokens:
        return text, tokenize(text)
    else:
        diff = abs(currlen - max_tokens)
        tokens = tokens[:-diff]
        currlen = len(tokens)
    return decode(tokens), currlen


def scrape_site(url, max_tokens):
    try:  # Thanks cybertimon for part of the script that finally made me implement scraping.
        response = requests.get(url, timeout=3, impersonate="chrome110")
        content_type = response.headers.get('content-type')
        if url.endswith(".pdf") or 'application/pdf' in content_type:
            text = ""
            for x in get_pdf_from_url(url).pages:
                text += x.extract_text()
        else:
            
            #soup = BeautifulSoup(response.text, "lxml")
            #text = soup.get_text()
            text = extract(response.text)

        text = text.strip()
        #text = text.replace("\n", "")
        text = url + "\n" + text
        print("BEFORE SHORTENING:", text)
        text, token_count = shorten_text(text, max_tokens)
        print("AFTER SHORTENING:", text)
        return text
    except Exception as e:
        print(e)
        return "Error: Requested site couldn't be viewed. Please inform in your response that the informations may not be up to date or correct."
