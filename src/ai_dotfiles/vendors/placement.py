"""Place a :class:`FetchedItem` into the catalog and write its ``.source``.

Takes the staged directory prepared by a vendor's ``fetch`` and moves
it into the appropriate ``catalog/<kind>s/<name>/`` location, then
drops a ``.source`` file alongside the moved content.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ai_dotfiles.core.errors import ElementError
from ai_dotfiles.vendors import source_file
from ai_dotfiles.vendors.base import FetchedItem


def place_item(
    item: FetchedItem,
    *,
    catalog_root: Path,
    force: bool,
    vendor_name: str,
) -> Path:
    """Move ``item.source_dir`` into the catalog and write ``.source``.

    Destination: ``catalog_root / f"{item.kind}s" / item.name``.

    Args:
        item: The fetched item produced by a vendor.
        catalog_root: Root of the catalog (``~/.ai-dotfiles/catalog``).
        force: If the destination already exists, overwrite it.
        vendor_name: Vendor plugin name recorded in ``.source``.

    Returns:
        Final destination path.

    Raises:
        ElementError: If destination exists and ``force`` is ``False``.
        FileNotFoundError: If ``item.source_dir`` does not exist
            (propagated from :func:`shutil.move`).
    """
    kind_dir = catalog_root / f"{item.kind}s"
    kind_dir.mkdir(parents=True, exist_ok=True)

    destination = kind_dir / item.name

    if destination.exists():
        if not force:
            raise ElementError(
                f"Already exists: {destination}. Use --force to overwrite."
            )
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    shutil.move(str(item.source_dir), str(destination))

    source_file.write(
        destination,
        vendor=vendor_name,
        origin=item.origin,
        tool="ai-dotfiles vendor",
        license=item.license,
    )

    return destination
