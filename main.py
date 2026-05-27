import base64
import io
import os

from src.lgx import LGX
from src.core.predicate.predicate_container import PredicateContainer

import pypdfium2 as pdfium
from PIL import Image


def pdf_to_images(pdf_path: str, dpi: int = 300) -> list:
    pdf = pdfium.PdfDocument(pdf_path)
    images = []
    scale = dpi / 72

    for page in pdf:
        bitmap = page.render(scale=scale)
        img = bitmap.to_pil()
        images.append(img.convert("RGB"))

    return images


@LGX.after_inference("robot_command")
def on_robot_command(facts: list[dict]):
    for cmd in facts:
        print(cmd)


if __name__ == "__main__":
    for model in ["gemma4:e4b", "gemma4:31b"]:
        for file in ["./0.pdf", "./1.pdf", "./3.pdf"]:

            print(f"Processing file: {file} with model: {model}")

            lgx_instance = LGX(
                "behaviour/behaviour.lgx.yml",
                "applications/lgx.yml",
                model
            )

            first_page = True
            context = "Describe the actions being performed in this image."

            for page in pdf_to_images(file):

                buffered = io.BytesIO()
                page.save(buffered, format="JPEG", quality=90)
                base64_string = base64.b64encode(buffered.getvalue()).decode("utf-8")
                result = lgx_instance.infer(context, base64_string).extracted_preds
                print("Result: ", result)

                if first_page:
                    first_page = False
                    context = result
                else:
                    context += "\n" + result

            with open(f"result_{model.replace(':', '_')}_{file.replace("./","").replace(".pdf","")}.txt", "w") as f:
                f.write(context)