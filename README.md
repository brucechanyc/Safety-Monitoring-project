# From Reactive to Proactive: A Camera-Based Safety Vest Compliance AI Agent

**NPSC3000 – Research, Leadership and Entrepreneurship in Science (Honours), Curtin University, 2026**
Author: Bruce Chan · Supervisor: Dan Marrable

This project turns the Innovation Central Perth (ICP) Living Lab AI assistant into a *proactive* agent. The agent watches the lab's Meraki cameras and flags people who are not wearing a hi-vis safety vest, with no human prompt needed.

The system has two parts:

- **Detection:** a dedicated object detector (YOLO26m) runs on every frame, so we don't send each frame to an LLM, which is slow and costly.
- **Reasoning and reporting:** an LLM (Gemini, via n8n workflows) handles these.

The full write-up is in [`docs/reports/NPSC3000 Final Report.pdf`](docs/reports/).

---

## Pipeline

```
Meraki cameras ──► meraki-person-capture ──► raw frames with people (class 0: person_no_vest)
                                                   │
                                                   ▼
                                     dataset-tools/add_hivis_vest.py
                              (Gemini image editing adds a hi-vis vest → class 1: person_vest)
                                                   │
                                                   ▼
                                     dataset-tools/build_yolo_dataset.py
                              (auto-labels person boxes, makes train/val split + data.yaml)
                                                   │
                                                   ▼
                                     training/train_yolo26_hivis_colab.ipynb
                                         (YOLO26m fine-tuned on Google Colab)
                                                   │
                                                   ▼
                                     results/hivis_yolo26m/best.pt
                                                   │
                                                   ▼
                       safety-monitor (live camera snapshots → n8n webhooks → Gemini reports)
```

## Repository layout

| Path | Contents |
|---|---|
| `code/meraki-person-capture/` | Takes a snapshot from three Meraki cameras every ~5 s during working hours (07:00–18:00). It runs YOLO26n person detection and keeps only the frames that contain a person. Has its own [README](code/meraki-person-capture/README.md). |
| `code/dataset-tools/add_hivis_vest.py` | Uses Gemini (`gemini-2.5-flash` to classify, `gemini-2.5-flash-image` to edit) to add a yellow hi-vis vest to the people in captured frames. |
| `code/dataset-tools/build_yolo_dataset.py` | Builds an Ultralytics-format dataset. A pretrained YOLO model auto-detects person boxes, and each box is labelled by the image's source folder (original → `person_no_vest`, edited → `person_vest`). |
| `code/training/train_yolo26_hivis_colab.ipynb` | Colab notebook used to train YOLO26m on the dataset. |
| `code/safety-monitor/` | Live monitoring loop. During working hours it pulls Meraki snapshots and sends them to n8n webhooks for the PPE, hazard, checks and report workflows. |
| `results/hivis_yolo26m/` | Final training run: `best.pt` weights, `results.csv`, `args.yaml`, PR/P/R/F1 curves, confusion matrices, and train/val batch previews. |
| `docs/reports/` | Final report, project proposal, project management plan, and YOLO literature review. |

## Results

YOLO26m was trained from `yolo26m.pt` with imgsz 640, batch 16, up to 200 epochs and early-stopping patience 20. Training stopped after 127 epochs, and the best epoch was **107**:

| Metric (validation) | Value |
|---|---|
| Precision | 0.888 |
| Recall | 0.938 |
| mAP50 | **0.955** |
| mAP50-95 | **0.861** |

### ⚠️ These scores are too optimistic

The train and validation sets were split at random at the frame level. The cameras capture a frame every ~5 seconds, so 303 of the 321 validation frames (~94%) were taken within 30 seconds of a training frame. The model was therefore validated on images almost identical to the ones it trained on.

The numbers show how high a YOLO model can score on near-duplicate data, not how it would perform on new days or scenes. Future work should split the data by time (by day or capture session) or by camera, and test on a held-out period. See the final report for the full analysis.

## Running the code

Each component reads credentials from environment variables or a `.env` file. **No keys are included in this repository.**

```bash
pip install -r code/meraki-person-capture/requirements.txt
cp code/meraki-person-capture/.env.example code/meraki-person-capture/.env   # then fill in your values
python code/meraki-person-capture/main.py
```

| Variable | Used by |
|---|---|
| `MERAKI_API_KEY`, `MERAKI_ORG_ID`, `MERAKI_SERIALS` | meraki-person-capture |
| `MERAKI_API_KEY`, `MERAKI_SERIAL`, `N8N_BASE_URL`, `*_WEBHOOK_PATH` | safety-monitor |
| `GEMINI_API_KEY` | dataset-tools/add_hivis_vest.py |

To use the trained detector directly:

```python
from ultralytics import YOLO
model = YOLO("results/hivis_yolo26m/best.pt")
model.predict("image.jpg", conf=0.25)   # classes: 0 = person_no_vest, 1 = person_vest
```

## Data

The image dataset (~825 original frames from the ICP Living Lab cameras plus the AI-edited vest versions, ~4.8 GB) is **not included**. It contains CCTV footage of real people and is too large for GitHub. It is available on request from the author.
