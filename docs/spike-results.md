# remove-portrait spike results

This records the options tested before settling on the current tool shape.

## Current default

- Backend: RobustVideoMatting (RVM), MobileNetV3 weights.
- Device: PyTorch CUDA.
- Output: full-frame ProRes 4444 `.mov` with alpha.
- Dimensions: preserve the source frame size by default.
- Cropping: not used. The camera layer should stay full-frame so movement
  inside the shot does not change positioning in Resolve.

## RVM

RVM is the default because it is video-native, streams frames, runs on CUDA, and
does not require a manual first-frame mask.

Results from the test clips:

- `test.mkv`, 3840x2160, 21.44s: about 78s runtime with ProRes 4444 output.
- `test.mkv`, full-size ProRes 4444 output: about 852 MB.
- `09-39-33-cam.mkv`, first 60s, 3840x2160: about 3m26s runtime.
- `09-39-33-cam.mkv`, first 60s ProRes 4444 output: about 2.33 GiB.

Quality was good enough for a first proper tool, but not perfect around hair,
hood, chair edges, desk, and microphone.

## rembg

`rembg` with `u2net_human_seg` worked, and ONNX Runtime CUDA was available, but
it was too slow for 4K video in this workflow. Early runs were around 0.6s per
frame on the small test file after GPU setup, which was still too slow for
right-click use on longer clips.

The backend is kept as a fallback because it is useful for comparison and model
tuning, but it is no longer the default.

## Codecs

`qtrle` was Resolve-friendly but huge. A 3s full-size test could be around 2 GB.

ProRes 4444 kept alpha, imported in Resolve, and was much smaller:

- 3s full-size sample: about 114 MB.
- 21.44s full-size `test.mkv`: about 852 MB.

The files are still large because alpha video needs RGB plus transparency in an
editing codec. Filmora likely keeps AI portrait as a timeline effect and exports
the final composited MP4, so it does not always create a 4K alpha intermediate.

## MatAnyone / MatAnyone2

MatAnyone2 ran on CUDA after installing a few extra dependencies and patching
its local output writer. It produced cleaner and more stable edges than plain
RVM on a 3s 1024x576 sample.

It was not chosen because it requires a first-frame segmentation mask. When the
seed mask included the chair and background objects, MatAnyone2 preserved those
objects faithfully. That moves the hard problem upstream instead of removing it.

MatAnyone2 also loads the whole input clip into memory in its reference
inference script, which is not a good fit for long 4K right-click processing
without a rewrite.

## VideoMaMa

VideoMaMa was considered but not spiked into the tool. It looked more like a
research/generative matting pipeline than a practical right-click processor:
image-sequence style inputs, mask dependencies, heavier setup, and lower default
working resolutions than native 4K.

## Things deliberately not done

- No crop-to-subject. It would reduce output size, but it would make Resolve
  positioning harder when the speaker moves around the camera frame.
- No MatAnyone backend. It needs a reliable mask source first.
- No final-composite MP4 output. That would be much smaller, but it would remove
  the separate transparent camera layer needed for editing.
