from typing import List
from PIL import Image
from models.region_data import RegionData
from models.tile_order_model import TileOrderModel


class ImageService:
    @staticmethod
    def load_rgba_image(image_path: str) -> Image.Image:
        with Image.open(image_path) as img:
            return img.convert("RGBA")

    @staticmethod
    def is_fully_transparent(image: Image.Image) -> bool:
        rgba = image if image.mode == "RGBA" else image.convert("RGBA")
        alpha_extrema = rgba.getchannel("A").getextrema()
        if alpha_extrema is None:
            return True
        return alpha_extrema[1] == 0

    @staticmethod
    def crop_region(source_img: Image.Image, region: RegionData) -> Image.Image:
        left = max(0, region.x)
        top = max(0, region.y)
        right = min(source_img.width, region.x + region.width)
        bottom = min(source_img.height, region.y + region.height)
        if right <= left or bottom <= top:
            return Image.new("RGBA", (max(1, region.width), max(1, region.height)), (0, 0, 0, 0))
        return source_img.crop((left, top, right, bottom))

    @staticmethod
    def crop_tile(
        region_img: Image.Image,
        col: int,
        row: int,
        tile_w: int,
        tile_h: int,
    ) -> Image.Image:
        left = col * tile_w
        top = row * tile_h
        right = left + tile_w
        bottom = top + tile_h
        return region_img.crop((left, top, right, bottom))

    @classmethod
    def compute_auto_slice_regions(
        cls,
        source_img: Image.Image,
        cell_w: int,
        cell_h: int,
        offset_x: int = 0,
        offset_y: int = 0,
        padding_x: int = 0,
        padding_y: int = 0,
        tile_w: int = 16,
        tile_h: int = 16,
        name_prefix: str = "Region",
        skip_transparent: bool = True,
        default_tile_order_path: str = "",
    ) -> List[RegionData]:
        regions: List[RegionData] = []
        if cell_w <= 0 or cell_h <= 0:
            return regions

        img_w, img_h = source_img.size
        idx = 0
        y = offset_y
        while y + cell_h <= img_h:
            x = offset_x
            while x + cell_w <= img_w:
                candidate = RegionData(
                    base_name=f"{name_prefix}_{idx:02d}",
                    x=x,
                    y=y,
                    width=cell_w,
                    height=cell_h,
                    tile_width=tile_w,
                    tile_height=tile_h,
                    tile_order_path=default_tile_order_path,
                )
                if skip_transparent:
                    cropped = cls.crop_region(source_img, candidate)
                    if cls.is_fully_transparent(cropped):
                        x += cell_w + padding_x
                        continue

                regions.append(candidate)
                idx += 1
                x += cell_w + padding_x
            y += cell_h + padding_y

        return regions

    @classmethod
    def generate_sequential_tile_order(
        cls,
        region_img: Image.Image,
        tile_w: int = 16,
        tile_h: int = 16,
        skip_transparent: bool = True,
    ) -> TileOrderModel:
        cols = region_img.width // tile_w if tile_w > 0 else 0
        rows = region_img.height // tile_h if tile_h > 0 else 0
        model = TileOrderModel(
            cols=cols,
            rows=rows,
            tile_width=tile_w,
            tile_height=tile_h,
        )
        for r in range(rows):
            for c in range(cols):
                if skip_transparent:
                    tile_img = cls.crop_tile(region_img, c, r, tile_w, tile_h)
                    if cls.is_fully_transparent(tile_img):
                        continue
                model.assign_next(c, r)
        return model
