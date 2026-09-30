"""Optional offline SmolVLM path. Disabled until dependencies/weights are supplied."""

from __future__ import annotations


def inspect_screenshot(image_path, model_directory, config):
    if not config.get("enabled"):
        return {"status": "disabled", "reason": "No vision inference required for Phase 0"}
    import torch
    from PIL import Image
    from transformers import AutoModelForVision2Seq, AutoProcessor

    processor = AutoProcessor.from_pretrained(model_directory, local_files_only=True)
    model = AutoModelForVision2Seq.from_pretrained(
        model_directory, local_files_only=True, torch_dtype=torch.float32
    )
    image = Image.open(image_path).convert("RGB")
    image.thumbnail((config["max_image_edge"], config["max_image_edge"]))
    messages = [{"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Describe the visible controls and feedback in this local fixture."},
    ]}]
    prompt = processor.apply_chat_template(messages, add_generation_prompt=True)
    inputs = processor(text=prompt, images=[image], return_tensors="pt")
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=config["max_output_tokens"], do_sample=False)
    return {"status": "inspected", "text": processor.decode(
        output[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True
    )}
