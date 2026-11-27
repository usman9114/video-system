# Final-cut lab: 01_n8n_automation_v6 (promo)

**Verdict: FAIL: loudness, lipsync**

1080x1350 @ 30.0 fps, 46.03 s

| Check | Status | Detail |
|---|---|---|
| Loudness | fail | -14.0 LUFS (target -14), true peak -1.4 dB (max -1.5) |
| Script vs what is heard | pass | WER 0.9% (max 8%); missing 'the' |
| Lip-sync (SyncNet, min 6.887) | fail | 0.0-10.2s LSE-C 3.898 off 3, 11.5-23.0s LSE-C 6.05 off 2, 25.2-32.6s LSE-C 5.638 off 1, 33.8-43.6s LSE-C 4.03 off 2 |
| No cut while talking | pass | 0 bad of 7 cuts   |
| Black frames | pass | none |
| Freezes | pass | none |
| Touch-up: face detail (blend 0.35) | rejected | 1236/1381 frames; face SSIM p05 0.9938 (min 0.95); SyncNet drop 0.0s 3.898→3.861 (+0.9%), 11.5s 6.05→5.962 (+1.4%), 25.2s 5.638→5.578 (+1.1%), 33.8s 4.03→3.889 (+3.5%) |

Kaggle 2x T4: gpu0 mean util 35.6%, busy 44.3% of samples, peak 10845 MB; gpu1 mean util 43.9%, busy 55.1% of samples, peak 1635 MB; lanes {"gpu0": {"rc": 0, "seconds": 849.7, "gpu": 0, "steps": [{"step": "lane_touchup.py", "rc": 0, "seconds": 533.6}, {"step": "lane_listen.py", "rc": 0, "seconds": 316.1}]}, "gpu1": {"rc": 0, "seconds": 1047.0, "gpu": 1, "steps": [{"step": "lane_touchup.py", "rc": 0, "seconds": 715.8}, {"step": "lane_finish.py", "rc": 0, "seconds": 331.2}]}}; session 1096.6 s
