import base64
import json
import random
import urllib.parse
import urllib.request
import uuid
import os
import websocket
import re
from openai import OpenAI
import Shared_vars

openaiclient = OpenAI(
    base_url=f"{Shared_vars.API_ENDPOINT_URI}v1",
    api_key=Shared_vars.API_KEY,
)

from pathlib import Path
from prompts import getsdprompts

client_id = str(uuid.uuid4())
with open(
    os.path.join(Path(os.path.abspath(__file__)).parent, "comfyui_workflow_lcm.json")
) as workflow:
    prompt_text_lcm = json.load(workflow)
with open(
    os.path.join(
        Path(os.path.abspath(__file__)).parent, "comfyui_workflow_turbovision.json"
    )
) as workflow:
    prompt_text_turbovision = json.load(workflow)


def queue_prompt(prompt, server_address):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode("utf-8")
    req = urllib.request.Request("http://{}/prompt".format(server_address), data=data)
    return json.loads(urllib.request.urlopen(req).read())


def get_image(filename, subfolder, folder_type, server_address):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen(
        "http://{}/view?{}".format(server_address, url_values)
    ) as response:
        return response.read()


def get_history(prompt_id, server_address):
    with urllib.request.urlopen(
        "http://{}/history/{}".format(server_address, prompt_id)
    ) as response:
        return json.loads(response.read())


def get_images(ws, prompt, server_address):
    prompt_id = queue_prompt(prompt, server_address)["prompt_id"]
    output_images = {}
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message["type"] == "executing":
                data = message["data"]
                if data["node"] is None and data["prompt_id"] == prompt_id:
                    break  # Execution is done
        else:
            continue  # previews are binary data

    history = get_history(prompt_id, server_address)[prompt_id]
    for o in history["outputs"]:
        for node_id in history["outputs"]:
            node_output = history["outputs"][node_id]
            if "images" in node_output:
                images_output = []
                for image in node_output["images"]:
                    image_data = get_image(
                        image["filename"],
                        image["subfolder"],
                        image["type"],
                        server_address,
                    )
                    images_output.append(image_data)
            output_images[node_id] = images_output

    return output_images


def generate(prmpt, server_address, seed=0, width=1024, height=1024):
    prompt = prompt_text_turbovision
    prompt["6"]["inputs"]["text"] = prmpt
    if not seed == 0:
        prompt["3"]["inputs"]["seed"] = seed
    else:
        seeed = random.randint(2000002406736107, 3778562406736107)
        print(f"Seed: {seeed}")
        prompt["3"]["inputs"]["seed"] = seeed
    prompt["5"]["inputs"]["width"] = width
    prompt["5"]["inputs"]["height"] = height
    ws = websocket.WebSocket()
    ws.connect("ws://{}/ws?clientId={}".format(server_address, client_id))
    images = get_images(ws, prompt, server_address)
    image = []
    for node_id in images:
        for image_data in images[node_id]:
            image.append(base64.b64encode((image_data)).decode("utf-8"))
    return image


def aspect2res(inp):
    aspect = ""
    for x in inp.split(","):
        if "x" in x or ":" in x:
            for p in x.split(" "):
                if "x" in p or ":" in p:
                    aspect = p
                    print(f"Gotten aspect: {p}")
                    break
    aspect = aspect.replace(":", "x").replace("1920x1080", "16x9")
    aspects = {}
    aspects["16x9"] = ["1365", "768"]
    aspects["9x16"] = ["768", "1344"]
    aspects["4x3"] = ["1182", "886"]
    if not aspect == "":
        try:
            return aspects[aspect]
        except KeyError:
            return ["1024", "1024"]
    else:
        return ["1024", "1024"]


def imagegen(msg):
    replyid = False
    imgtoimg = False
    sample = "1. standing white Persian cat, filmed with a Canon EOS R6, 70-200mm lens, high quality\n2. standing white Persian cat, photo, filmed with a Canon EOS R6, 70-200mm lens, high quality"

    payload = getsdprompts(replyid, msg, imgtoimg)
    chat_completion = openaiclient.chat.completions.create(
        model="gpt-4",
        messages=payload,
        temperature=0.1,
        max_tokens=150,
        stop=["</s>", "###", "<|im_end|>", "<|im_start|>"],
    )
    rfn = chat_completion.choices[0].message.content
    output = re.split(r"\d\.", rfn)
    print(output)
    tosend = ""
    try:
        tosend = list(output)[1].replace("\n", "")
        print(f"Prompt: {tosend}")
    except Exception:
        print(f"Error: {traceback.format_exc()}")

        tosend = "".join(output)
        print(f"Prompt: {tosend}")
        tosend = f"{tosend}"
    res = aspect2res(tosend)
    x = generate(
        tosend,
        Shared_vars.config.enabled_features["image_generation"]["server_address"],
        width=res[0],
        height=res[1],
    )[0]
    return [x, tosend]
