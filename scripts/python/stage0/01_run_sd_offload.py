"""Stage 0 step 01: offload a camera card to the SSD photo taxonomy.

One run per card insert: detect card and SSD, inventory with exiftool,
skip files already in the offload ledger, segment shoots by capture-time
gaps, suggest a category with Apple Vision, ask the operator only what
cannot be inferred, then scaffold, copy with SHA-256 verification, and
write a per-run manifest. Nothing is ever deleted from the card.

Examples:

    python3 scripts/python/stage0/01_run_sd_offload.py
    python3 scripts/python/stage0/01_run_sd_offload.py --card /Volumes/Untitled --dry-run
    python3 scripts/python/stage0/01_run_sd_offload.py --refile "/Volumes/.../_Inbox/2026-05-10 – Unsorted"
    python3 scripts/python/stage0/01_run_sd_offload.py install-agent
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import plistlib
import subprocess
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.python.common import ensure_parent_dir
from scripts.python.stage0.classify import (
    ClassifierUnavailable,
    ShootClassification,
    VisionAnalyzer,
    classify_shoot,
    reverse_geocode,
)
from scripts.python.stage0.config import DEFAULT_CONFIG_PATH, OffloadConfig, load_config
from scripts.python.stage0.dialogs import (
    DialogBackend,
    FilingDecision,
    FolderSource,
    OsascriptDialogs,
    Questionnaire,
    ShootPrompt,
    SilentDialogs,
)
from scripts.python.stage0.inventory import (
    SHOOT_SCAN_ROOTS,
    CardFile,
    Shoot,
    build_inventory,
    exiftool_reader,
    filter_new,
    resolve_exiftool,
    segment_shoots,
)
from scripts.python.stage0.taxonomy import EmptyTaxonomy, TaxonomyReader, inbox_relpath
from scripts.python.stage0.transfer import (
    CollisionError,
    OffloadLedger,
    TransferRecord,
    VerificationError,
    copy_verified,
    move_verified,
    sha256_file,
    transfer_files,
)
from scripts.python.stage0.volumes import (
    AccessDeniedError,
    VolumeIdentity,
    access_denied,
    find_cards,
    find_volume_by_uuid,
    is_camera_card,
    volume_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE_DIR = Path(__file__).resolve().parent
AGENT_LABEL = "com.jbphoto.sd-offload"
AGENT_TEMPLATE = STAGE_DIR / "launchd" / f"{AGENT_LABEL}.plist"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
STAGE_NAME = "stage0_sd_ingest_offload"


@dataclass(frozen=True)
class ShootPlan:
    """One shoot with its classification and filing decision."""

    shoot: Shoot
    classification: ShootClassification
    decision: FilingDecision


def log(message: str) -> None:
    """Print a timestamped line (captured in agent.out under launchd)."""
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"{stamp} {message}", flush=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the Stage 0 offload orchestrator."""
    parser = argparse.ArgumentParser(
        description="Offload a Sony camera card to the SSD photo taxonomy."
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--card", type=Path, help="Card mount point (default: auto-detect).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inventory, classify, and plan only; write nothing to the SSD or outputs.",
    )
    parser.add_argument(
        "--no-dialog",
        action="store_true",
        help="Skip dialogs; every shoot is planned for the _Inbox fallback.",
    )
    parser.add_argument(
        "--refile",
        type=Path,
        metavar="INBOX_FOLDER",
        help="File an existing _Inbox shoot folder through the questionnaire.",
    )
    subparsers = parser.add_subparsers(dest="command")
    install = subparsers.add_parser(
        "install-agent", help="Install the StartOnMount launchd agent."
    )
    install.add_argument(
        "--no-load",
        action="store_true",
        help="Write the plist to ~/Library/LaunchAgents without loading it.",
    )
    return parser.parse_args(argv)


@contextmanager
def run_lock(state_dir: Path) -> Iterator[bool]:
    """Hold an exclusive lock so overlapping mount events do not run twice."""
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / "run.lock").open("w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_ordered_json(path: Path, payload: dict[str, object]) -> Path:
    """Write JSON while preserving semantic key order."""
    target = ensure_parent_dir(path)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return target


def make_analyzer() -> VisionAnalyzer | None:
    """Return the Vision analyzer, or None with a logged reason."""
    try:
        return VisionAnalyzer()
    except ClassifierUnavailable as exc:
        log(f"warning: {exc}")
        return None


def time_range(shoot: Shoot) -> str:
    """Return a human-readable capture window for dialogs."""
    start, end = shoot.start, shoot.end
    if start.date() == end.date():
        return f"{start:%a %d %b %Y}, {start:%H:%M}–{end:%H:%M}"
    return f"{start:%a %d %b %Y %H:%M} – {end:%a %d %b %Y %H:%M}"


def shoot_prompt(shoot: Shoot, classification: ShootClassification) -> ShootPrompt:
    """Build what the questionnaire shows for one shoot."""
    return ShootPrompt(
        shoot_id=shoot.shoot_id,
        file_count=len(shoot.files),
        time_range=time_range(shoot),
        year=shoot.start.year,
        candidates=classification.candidates,
        auto_accepted_category=classification.auto_accepted_category,
        location_suggestion=classification.location_suggestion,
    )


def inbox_decision(config: OffloadConfig, shoot: Shoot) -> FilingDecision:
    """Return the unsorted-inbox fallback for a shoot."""
    return FilingDecision(
        relpath=inbox_relpath(config.inbox_folder, shoot.start.date()),
        filing="inbox_unsorted",
        merge_into_existing=False,
    )


def short_path(relpath: PurePosixPath) -> str:
    """Shorten a destination for notifications: `People/…/Mangos 2026`."""
    parts = relpath.parts
    if len(parts) <= 3:
        return str(relpath)
    return f"{parts[0]}/…/{parts[-2]}/{parts[-1]}"


def check_photo_root(photo_root: Path) -> None:
    """Fail early with an actionable message when the photo root is unusable."""
    try:
        os.listdir(photo_root)
    except PermissionError as exc:
        raise access_denied(photo_root) from exc
    except FileNotFoundError as exc:
        raise SystemExit(f"Photo root not found on the SSD: {photo_root}") from exc


def plan_shoots(
    shoots: Sequence[Shoot],
    config: OffloadConfig,
    exiftool: str,
    dialogs: DialogBackend,
    folders: FolderSource,
    use_dialogs: bool,
) -> list[ShootPlan]:
    """Classify each shoot and resolve its filing decision."""
    analyzer = make_analyzer()
    geocoder = None
    if config.classification.reverse_geocode:
        timeout = config.classification.geocode_timeout_seconds

        def geocoder(latitude: float, longitude: float) -> str | None:
            return reverse_geocode(latitude, longitude, timeout)

    questionnaire = Questionnaire(dialogs, folders, config)
    plans: list[ShootPlan] = []
    for shoot in shoots:
        classification = classify_shoot(
            shoot, analyzer, config.classification, exiftool, geocoder
        )
        decision = None
        if use_dialogs:
            decision = questionnaire.run(shoot_prompt(shoot, classification))
        if decision is None:
            decision = inbox_decision(config, shoot)
        plans.append(ShootPlan(shoot, classification, decision))
    return plans


def print_plan(plans: Sequence[ShootPlan], photo_root: Path | None) -> None:
    """Print shoots, classifier suggestions, and planned destinations."""
    for plan in plans:
        shoot = plan.shoot
        log(
            f"shoot {shoot.shoot_id}: {len(shoot.files)} files "
            f"({shoot.photo_count} photos, {shoot.video_count} videos), {time_range(shoot)}"
        )
        classification = plan.classification
        if classification.candidates:
            ranked = ", ".join(
                f"{candidate.category} {candidate.confidence:.2f}"
                for candidate in classification.candidates[:3]
            )
            log(f"  suggested categories ({classification.classifier}): {ranked}")
        else:
            log(f"  suggested categories: none ({classification.classifier})")
        if classification.top_labels:
            labels = ", ".join(f"{label} {score:.2f}" for label, score in classification.top_labels[:5])
            log(f"  top labels: {labels}")
        if classification.auto_accepted_category:
            log(f"  auto-accepted category: {classification.auto_accepted_category}")
        if classification.location_suggestion:
            log(f"  location suggestion: {classification.location_suggestion}")
        for note in classification.notes:
            log(f"  note: {note}")
        root = photo_root if photo_root else Path("<SSD>")
        destination = root / plan.decision.relpath
        log(f"  planned destination ({plan.decision.filing}): {destination}")
        log(f"    Photo/RAW{' + Video/RAW' if shoot.has_video else ''}")


def build_run_manifest(
    *,
    status: str,
    pipeline_step: str,
    source: dict[str, object],
    destination: dict[str, object],
    config: OffloadConfig,
    plans: Sequence[ShootPlan],
    records: dict[str, list[TransferRecord]],
    skipped_count: int,
    error: str | None,
) -> dict[str, object]:
    """Build the ordered per-run manifest payload."""
    all_records = [record for items in records.values() for record in items]
    shoots = []
    for plan in plans:
        shoot_records = records.get(plan.shoot.shoot_id, [])
        shoots.append(
            {
                "shoot_id": plan.shoot.shoot_id,
                "start_local": plan.shoot.start.isoformat(),
                "end_local": plan.shoot.end.isoformat(),
                "photo_count": plan.shoot.photo_count,
                "video_count": plan.shoot.video_count,
                "file_count": len(plan.shoot.files),
                **plan.decision.to_record(),
                "classifier_suggestions": plan.classification.to_record(),
                "files": [
                    {"shoot_id": plan.shoot.shoot_id, **record.to_record()}
                    for record in shoot_records
                ],
            }
        )
    return {
        "stage": STAGE_NAME,
        "status": status,
        "summary": {
            "shoot_count": len(plans),
            "file_count": sum(len(plan.shoot.files) for plan in plans),
            "transferred_count": sum(1 for record in all_records if record.status in {"copied", "moved"}),
            "already_present_count": sum(
                1 for record in all_records if record.status == "already_present"
            ),
            "skipped_by_ledger_count": skipped_count,
            "total_bytes": sum(record.file.size_bytes for record in all_records),
            "inbox_shoot_count": sum(
                1 for plan in plans if plan.decision.filing == "inbox_unsorted"
            ),
        },
        "pipeline_step": pipeline_step,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "error": error,
        "note": (
            "classifier_suggestions are ranked on-device Vision suggestions, not "
            "facts; answers contain only what the operator entered or confirmed."
        ),
        "source": source,
        "destination": destination,
        "config": {
            "path": str(config.source_path),
            "sha256": sha256_file(config.source_path),
        },
        "shoots": shoots,
    }


def manifest_path(config: OffloadConfig, label: str) -> Path:
    """Return outputs/stage0/offloads/<timestamp>_<label>.json."""
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return REPO_ROOT / config.manifest_dir / f"{stamp}_{label}.json"


def execute_plans(
    plans: Sequence[ShootPlan],
    photo_root: Path,
    ledger: OffloadLedger,
    source_label: str,
    refile: bool = False,
) -> tuple[dict[str, list[TransferRecord]], str | None]:
    """Transfer every planned shoot; stop at the first integrity error."""
    records: dict[str, list[TransferRecord]] = {}
    for plan in plans:
        shoot_dir = photo_root / plan.decision.relpath
        log(f"{'refiling' if refile else 'copying'} {plan.shoot.shoot_id} -> {shoot_dir}")
        try:
            records[plan.shoot.shoot_id] = transfer_files(
                plan.shoot.files,
                shoot_dir,
                ledger,
                source_label,
                plan.shoot.has_video,
                operation=move_verified if refile else copy_verified,
                event="refile" if refile else "offload",
            )
        except (CollisionError, VerificationError, OSError) as exc:
            return records, f"{plan.shoot.shoot_id}: {exc}"
    return records, None


def offload_card(
    card: Path,
    ssd: VolumeIdentity | None,
    config: OffloadConfig,
    args: argparse.Namespace,
    dialogs: DialogBackend,
) -> int:
    """Run the full offload for one card."""
    identity = volume_identity(card)
    log(f"card: {identity.volume_name} at {card}")
    ledger = OffloadLedger(config.state_dir / "ledger.jsonl")
    exiftool = resolve_exiftool(config.exiftool_path)
    files = build_inventory(card, exiftool_reader(exiftool))
    new, skipped = filter_new(files, ledger.known_keys())
    log(f"inventory: {len(files)} media files, {len(skipped)} already offloaded, {len(new)} new")
    if not new:
        dialogs.notify(f"Nothing new on {identity.volume_name}.")
        return 0

    photo_root = ssd.mount_point / config.photo_root if ssd else None
    folders: FolderSource = EmptyTaxonomy()
    if photo_root is not None:
        try:
            check_photo_root(photo_root)
            folders = TaxonomyReader(photo_root, frozenset({config.inbox_folder}))
        except AccessDeniedError as exc:
            if not args.dry_run:
                raise
            log(f"warning: {exc}")

    shoots = segment_shoots(new, config.gap_hours, config.split_on_date_change)
    log(f"segmented into {len(shoots)} shoot(s) at a {config.gap_hours:g} h gap")
    plans = plan_shoots(shoots, config, exiftool, dialogs, folders, not args.no_dialog)
    print_plan(plans, photo_root)
    if args.dry_run:
        log("dry run: nothing written to the SSD, ledger, or outputs.")
        return 0
    assert photo_root is not None and ssd is not None

    records, error = execute_plans(plans, photo_root, ledger, identity.label)
    manifest = build_run_manifest(
        status="failed" if error else "complete",
        pipeline_step="01_run_sd_offload",
        source={"kind": "camera_card", **identity.to_record()},
        destination={
            **ssd.to_record(),
            "photo_root": str(photo_root),
        },
        config=config,
        plans=plans,
        records=records,
        skipped_count=len(skipped),
        error=error,
    )
    target = write_ordered_json(manifest_path(config, identity.label), manifest)
    log(f"Wrote {target}")
    if error:
        log(f"error: {error}")
        dialogs.notify(f"Offload stopped: {error}")
        return 1
    file_count = sum(len(plan.shoot.files) for plan in plans)
    if len(plans) == 1:
        where = short_path(plans[0].decision.relpath)
    else:
        where = f"{len(plans)} shoots"
    dialogs.notify(f"Offloaded {file_count} files → {where}")
    return 0


def run_offload(args: argparse.Namespace, config: OffloadConfig, dialogs: DialogBackend) -> int:
    """Detect card(s) and SSD, then offload each card."""
    ssd = find_volume_by_uuid(config.ssd_volume_uuid)
    if args.card:
        card = args.card.resolve()
        if not is_camera_card(card):
            raise SystemExit(f"{card} is not a camera card (expected DCIM/ with a Sony layout).")
        cards = [card]
    else:
        cards = find_cards(exclude={ssd.mount_point} if ssd else None)
    if not cards:
        log("No camera card mounted; nothing to do.")
        return 0
    if ssd is None:
        if not args.dry_run:
            dialogs.notify(f"Plug in {config.ssd_display_name} to offload the SD card.")
            log(f"{config.ssd_display_name} ({config.ssd_volume_uuid}) is not mounted; exiting.")
            return 0
        log(f"warning: {config.ssd_display_name} not mounted; destinations shown relative.")
    status = 0
    for card in cards:
        status = max(status, offload_card(card, ssd, config, args, dialogs))
    return status


def run_refile(args: argparse.Namespace, config: OffloadConfig, dialogs: DialogBackend) -> int:
    """File an `_Inbox/<date> – Unsorted` folder through the questionnaire."""
    if args.no_dialog:
        raise SystemExit("--refile needs dialogs; remove --no-dialog.")
    ssd = find_volume_by_uuid(config.ssd_volume_uuid)
    if ssd is None:
        raise SystemExit(f"{config.ssd_display_name} is not mounted.")
    photo_root = ssd.mount_point / config.photo_root
    check_photo_root(photo_root)
    inbox_dir = args.refile.resolve()
    inbox_root = (photo_root / config.inbox_folder).resolve()
    if inbox_dir.parent != inbox_root or not inbox_dir.is_dir():
        raise SystemExit(f"--refile expects a folder directly inside {inbox_root}")

    exiftool = resolve_exiftool(config.exiftool_path)
    files: list[CardFile] = build_inventory(inbox_dir, exiftool_reader(exiftool), SHOOT_SCAN_ROOTS)
    if not files:
        raise SystemExit(f"No media under {inbox_dir}/Photo/RAW or Video/RAW.")
    shoot = Shoot(shoot_id=inbox_dir.name, files=tuple(files))
    folders = TaxonomyReader(photo_root, frozenset({config.inbox_folder}))
    plans = plan_shoots([shoot], config, exiftool, dialogs, folders, use_dialogs=True)
    if plans[0].decision.filing != "operator_confirmed":
        log("refile cancelled; folder left in the inbox.")
        return 0
    print_plan(plans, photo_root)
    if args.dry_run:
        log("dry run: nothing moved.")
        return 0

    ledger = OffloadLedger(config.state_dir / "ledger.jsonl")
    records, error = execute_plans(plans, photo_root, ledger, inbox_dir.name, refile=True)
    manifest = build_run_manifest(
        status="failed" if error else "complete",
        pipeline_step="01_run_sd_offload --refile",
        source={"kind": "inbox_folder", "path": str(inbox_dir)},
        destination={**ssd.to_record(), "photo_root": str(photo_root)},
        config=config,
        plans=plans,
        records=records,
        skipped_count=0,
        error=error,
    )
    target = write_ordered_json(manifest_path(config, "refile"), manifest)
    log(f"Wrote {target}")
    if error:
        dialogs.notify(f"Refile stopped: {error}")
        return 1
    for folder in sorted(inbox_dir.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
    if inbox_dir.is_dir() and not any(inbox_dir.iterdir()):
        inbox_dir.rmdir()
    dialogs.notify(f"Refiled {len(files)} files → {short_path(plans[0].decision.relpath)}")
    return 0


def install_agent(args: argparse.Namespace, config: OffloadConfig) -> int:
    """Render the launchd plist into ~/Library/LaunchAgents and load it."""
    venv_python = REPO_ROOT / ".venv" / "bin" / "python3"
    python = venv_python if venv_python.exists() else Path(sys.executable)
    rendered = (
        AGENT_TEMPLATE.read_text(encoding="utf-8")
        .replace("{{PYTHON}}", str(python))
        .replace("{{SCRIPT}}", str(Path(__file__).resolve()))
        .replace("{{REPO_ROOT}}", str(REPO_ROOT))
        .replace("{{STATE_DIR}}", str(config.state_dir))
    )
    plistlib.loads(rendered.encode("utf-8"))
    config.state_dir.mkdir(parents=True, exist_ok=True)
    target = LAUNCH_AGENTS_DIR / f"{AGENT_LABEL}.plist"
    ensure_parent_dir(target).write_text(rendered, encoding="utf-8")
    log(f"Wrote {target}")
    if args.no_load:
        return 0
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(target)], capture_output=True, check=False)
    completed = subprocess.run(
        ["launchctl", "bootstrap", domain, str(target)], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise SystemExit(f"launchctl bootstrap failed: {completed.stderr.strip()}")
    log(f"Loaded {AGENT_LABEL}; it runs whenever a volume mounts.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch install-agent, refile, or a normal offload run."""
    args = parse_args(argv)
    config = load_config(args.config)
    if args.command == "install-agent":
        return install_agent(args, config)
    dialogs: DialogBackend = (
        SilentDialogs()
        if args.no_dialog
        else OsascriptDialogs(config.dialogs.title, config.dialogs.timeout_seconds)
    )
    with run_lock(config.state_dir) as acquired:
        if not acquired:
            log("Another offload run is in progress; exiting.")
            return 0
        try:
            if args.refile:
                return run_refile(args, config, dialogs)
            return run_offload(args, config, dialogs)
        except AccessDeniedError as exc:
            log(f"error: {exc}")
            dialogs.notify("Offload blocked by macOS privacy settings; see agent.err.")
            print(str(exc), file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
