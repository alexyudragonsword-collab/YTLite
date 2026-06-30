---
name: image-slide-ocr-pptx
description: Convert slide screenshots or image-only PPTX decks into high-fidelity editable PPTX files by preserving raster imagery and overlaying visible editable OCR text in the original positions. Also supports merging generated PPTX files.
---

# Image Slide OCR to Editable PPTX

Use this skill when the user asks to convert a slide image, slide screenshot, or image-only PPTX into an editable PowerPoint while preserving the visual design. The key requirement is: keep images/backgrounds intact, OCR the text, and place visible editable text boxes in the same positions.

## When to use

Trigger this skill for requests like:

- “将这个图片转换成可编辑的 pptx，保持所有图像。”
- “把每页都是图片的 PPTX 转成可编辑 PPTX。”
- “文字识别出来，确保可以编辑。”
- “文本框是空的，重新生成可见文字。”
- “把这几个转换好的 PPTX 合并成一个。”

## Core principle

Do **not** create an invisible or transparent OCR layer. The PPTX must contain real, visible, editable text boxes. The user should be able to click the text and edit it in PowerPoint.

The preferred high-fidelity approach is:

1. Put the original image on the slide as a full-slide background.
2. Cover text regions with white or background-matched raster patches/shapes.
3. Overlay visible editable text boxes at the original coordinates.
4. Preserve all non-text images, icons, diagrams, logos, charts, and backgrounds.
5. Render-check the PPTX before delivery.

## Dependencies

Recommended tools:

- `python-pptx`
- `Pillow`
- `pytesseract` with `chi_sim+eng`
- `libreoffice` or `soffice` for render validation
- `pdftoppm` from poppler for PDF-to-PNG previews
- Optional: `pptxcompose` for robust PPTX merging

Install when needed:

```bash
pip install python-pptx pillow pytesseract pptxcompose
```

## Workflow

### 1. Inspect input

For a single image:

- Read image size.
- Create a one-slide PPTX with matching aspect ratio, typically 16:9.
- Add the image full-slide.

For image-only PPTX:

- Extract each page image or render each slide to PNG.
- Process each slide image independently.
- Merge generated pages.

For multiple PPTX files:

- Merge in the exact order requested by the user.

### 2. OCR and correction

Use OCR as a starting point only:

```bash
tesseract input.png stdout -l chi_sim+eng
```

Then manually correct common OCR errors using visual context. Preserve:

- Chinese punctuation and separators
- page numbers
- bullets
- title numbering
- colored emphasis words
- “一句话总结” footer text

### 3. Coordinate mapping

Use pixel coordinates from the source image and map them to PPTX coordinates:

```python
slide_width_in = 13.333333
slide_height_in = 7.5
x_in = x_px / image_width_px * slide_width_in
y_in = y_px / image_height_px * slide_height_in
w_in = w_px / image_width_px * slide_width_in
h_in = h_px / image_height_px * slide_height_in
```

### 4. Text overlay strategy

Use one of these strategies:

#### Strategy A: background image + cover patches + editable text
Best for high visual fidelity.

- Add the full original image as the background.
- Add white/background-matched patches over existing text regions.
- Add editable text over the patches.

Use a white image patch instead of a PPT shape if the renderer introduces shadows or unexpected borders.

#### Strategy B: crop non-text graphics + rebuild layout
Use when text density is high and cover patches damage design.

- Crop diagrams/images/logos from original.
- Rebuild cards, lines, titles, bullets as editable objects.
- Insert cropped images in their original positions.

### 5. Typography rules

- Chinese font: `Microsoft YaHei`; fallback: `SimHei`, `Noto Sans CJK SC`.
- Main title: deep blue, bold, large.
- Emphasis words: red, bold.
- Body text: black or deep blue, medium size.
- Captions: centered, deep blue, bold.
- Page number: black, bottom right.
- “内部交流”: red, inside red rounded rectangle when present.

### 6. Render validation

Always render before final delivery:

```bash
mkdir -p render_check
libreoffice --headless --convert-to pdf --outdir render_check output.pptx
pdftoppm -png render_check/output.pdf render_check/slide
```

Inspect the rendered PNG. Fix before delivery if any of these occur:

- text boxes are empty
- text is invisible
- duplicated original text creates severe ghosting
- line wrapping is wrong
- text overlaps images
- logo/page number/footer is clipped
- images are missing or distorted

## Implementation notes

- `python-pptx` textboxes should use `fill.background()` and `line.fill.background()` so they do not create visible boxes.
- For cover patches, use a small white PNG stretched over the target region to avoid LibreOffice rendering shadows from shapes.
- Do not set text fill transparency.
- If a textbox is only for editability but should not visually replace text, still make it visible enough to be usable or explain the limitation. Never return empty text boxes.
- For Chinese text, large boxes with smaller font sizes often render more reliably than tight boxes.

## Useful commands

Single image conversion with a manually prepared OCR/layout JSON:

```bash
python scripts/convert_image_to_editable_pptx.py input.png output.pptx --layout layout.json
```

Render check:

```bash
python scripts/render_check.py output.pptx render_check
```

Merge PPTX files:

```bash
python scripts/merge_pptx.py merged.pptx slide1.pptx slide2.pptx slide3.pptx
```

## Layout JSON format

```json
{
  "slide_width_in": 13.333333,
  "slide_height_in": 7.5,
  "patches": [
    {"x": 40, "y": 16, "w": 826, "h": 82, "color": "#FFFFFF"}
  ],
  "texts": [
    {
      "x": 50,
      "y": 26,
      "w": 810,
      "h": 46,
      "runs": [
        {"text": "9. 代理模型是第一性瓶颈突破口", "size": 29, "color": "#0B1E89", "bold": true}
      ],
      "align": "left",
      "font": "Microsoft YaHei"
    }
  ]
}
```

Coordinates are in source-image pixels.

## Quality bar

A result is acceptable only when:

- The slide visually resembles the uploaded image.
- Text is real PowerPoint text and can be edited.
- Major text is recognized and corrected.
- Non-text images are preserved.
- A render preview has been inspected.
