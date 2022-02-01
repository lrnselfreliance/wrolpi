from dataclasses import dataclass


@dataclass
class PBFPostRequest:
    pbf_url: str


@dataclass
class PBFPostResponse:
    success: str
