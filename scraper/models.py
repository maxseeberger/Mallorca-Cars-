from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class CarListing:
    source: str           # 'wallapop' | 'milanuncios' | 'coches_net' | 'cochesmallorca'
    source_id: str        # ID on the source platform
    title: str
    listing_url: str

    price: Optional[int] = None
    year: Optional[int] = None
    mileage: Optional[int] = None
    fuel: Optional[str] = None
    gearbox: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    location: Optional[str] = None
    image_url: Optional[str] = None      # primary thumbnail (first image)
    images: List[str] = field(default_factory=list)  # all gallery images
    description: Optional[str] = None

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if v is None:
                continue
            # Don't write empty images list — avoids overwriting existing DB data
            if k == 'images' and len(v) == 0:
                continue
            d[k] = v
        return d
