"""Import a field checkpoint or derive local acceptance gates from separate practice takes."""

from PIL import Image, ImageOps

from app.identity.appearance import ColorGrid
from app.identity.config import Config
from app.identity.tracker import valid_box
from .data import asset, read, save, sha, truth_key, verified
from .methods import Inputs


def collect(args):
    root = args.study
    if (root / "seal.json").exists():
        raise ValueError("Collection is sealed")
    public = read(root / "observations.json")
    truth = read(root / "truth.json")
    case = next((x for x in public["cases"] if x["id"] == args.case), None)
    if case is None:
        raise ValueError("Unknown case")
    if args.video:
        import cv2

        if args.at_ms is None or args.at_ms < 0:
            raise ValueError("A video requires a nonnegative --at-ms")
        video = cv2.VideoCapture(str(args.video))
        try:
            video.set(cv2.CAP_PROP_POS_MSEC, args.at_ms)
            ok, frame = video.read()
            if not ok:
                raise ValueError("Could not extract the requested video frame")
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        finally:
            video.release()
    else:
        with Image.open(args.image) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    valid_box(args.box, image.size)
    path = root / case["image"]
    if args.time_ms < 0 or (args.deadline_ms is not None and args.deadline_ms <= 0):
        raise ValueError("Invalid timestamp or freshness interval")
    case.update(
        box=args.box,
        time_ms=args.time_ms,
        deadline_ms=args.deadline_ms,
        gap=not args.continuous,
    )
    for field in ("prior", "second"):
        value = getattr(args, field)
        if value is not None:
            case[field] = None if value == "none" else value
    truth[args.case].update(body=args.body, identifiable=args.identifiable == "yes")
    with path.open("xb") as stream:
        image.save(stream, "JPEG", quality=95)
    save(root / "observations.json", public)
    save(root / "truth.json", truth)


def calibrate(root, path):
    data = verified(root)
    if (
        data.get("split") != "development"
        or sha(root / "truth.json") != read(root / "seal.json")["truth"]
    ):
        raise ValueError("Calibration requires sealed, separate development takes")
    truth = truth_key(root, data["cases"])
    inputs = Inputs(root, data, Config())
    positive, negative, margins = [], [], []
    for c in data["cases"]:
        key = truth[c["id"]]
        scores = inputs.local[c["id"]]["scores"]
        body = key["body"]
        if key["identifiable"] and body in ("A", "B"):
            good = scores[body]
            impostor = scores["A" if body == "B" else "B"]
            positive.append(good)
            negative.append(impostor)
            margins.append(good - impostor)
        else:
            negative.extend(scores.values())
    if (
        not positive
        or not negative
        or min(positive) <= max(negative)
        or min(margins) <= 0
    ):
        raise ValueError(
            "Development examples do not separate; leave local acceptance disabled"
        )
    if path.exists():
        raise ValueError("Calibration already exists")
    save(
        path,
        {
            "embedding_model": ColorGrid.name,
            "development_set": root.name,
            "synthetic_only": False,
            "development_image_sha256": sorted(
                {sha(asset(root, c["image"])) for c in data["cases"]}
            ),
            "gallery_hashes": {
                a: [sha(asset(root, f)) for f in files]
                for a, files in data["references"].items()
            },
            "appearance_min": (min(positive) + max(negative)) / 2,
            "appearance_margin": min(margins) / 2,
        },
    )
