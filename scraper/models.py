from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CarListing:
    source: str           # 'wallapop' | 'milanuncios' | 'coches_net'
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
    image_url: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}
