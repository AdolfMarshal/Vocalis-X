import shutil
import uuid
import os

def generate_audio(prompt):
    os.makedirs("output", exist_ok=True)

    filename = f"{uuid.uuid4()}.wav"
    output_path = f"output/{filename}"

    # Copy a dummy wav file
    shutil.copyfile("sample.wav", output_path)

    return output_path
