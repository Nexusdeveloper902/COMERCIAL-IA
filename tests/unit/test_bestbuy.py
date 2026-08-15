"""Best Buy scraper adapter tests (no network; mocked HTTP client)."""
from commercial_ai.scrapers.bestbuy import BestBuyScraper


class _FakeHttp:
    """Returns canned Best Buy API JSON for any URL."""

    def __init__(self, pages: list[dict]):
        self._pages = pages
        self.calls = 0

    def get_json(self, url, use_cache=True):
        if self.calls >= len(self._pages):
            return {"products": [], "total": 0}
        page = self._pages[self.calls]
        self.calls += 1
        return page


def _product(name="Logitech G502 X", sku=12345, upc="09785512345",
             manufacturer="Logitech", model_number="910-006765",
             sale_price=149.99, details=None):
    return {
        "sku": sku, "upc": upc, "name": name, "manufacturer": manufacturer,
        "modelNumber": model_number, "regularPrice": 169.99, "salePrice": sale_price,
        "onSale": True, "availability": "Available", "condition": "New",
        "shortDescription": "Wireless gaming mouse",
        "longDescription": "<p>High performance wireless gaming mouse.</p>",
        "images": [{"href": "https://images.example/img.jpg"}],
        "details": details or [{"name": "Weight", "value": "106 g"}],
    }


def test_bestbuy_yields_raw_records():
    page = {"products": [_product()], "total": 1}
    http = _FakeHttp([page])
    scraper = BestBuyScraper(api_key="fakekey", http_client=http, max_pages=1)
    records = list(scraper.iter_raw_records())
    assert len(records) == 1
    r = records[0]
    assert r.source.domain == "www.bestbuy.com"
    assert r.source.source_kind == "scraped"
    raw = r.raw
    assert raw["title"] == "Logitech G502 X"
    assert raw["price_text"] == "$149.99"
    assert raw["currency"] == "USD"
    assert raw["_bby_upc"] == "09785512345"
    assert raw["_bby_manufacturer"] == "Logitech"
    assert raw["_bby_model_number"] == "910-006765"
    assert raw["specifications"]["Weight"] == "106 g"
    assert raw["images"] == ["https://images.example/img.jpg"]


def test_bestbuy_no_key_yields_nothing():
    scraper = BestBuyScraper(api_key="", http_client=_FakeHttp([]))
    assert list(scraper.iter_raw_records()) == []


def test_bestbuy_paginates_and_stops():
    # page 1 has 25 (page_size), total 30 -> page 2 has 5 -> stop.
    page1 = {"products": [_product(sku=i) for i in range(25)], "total": 30}
    page2 = {"products": [_product(sku=i) for i in range(25, 30)], "total": 30}
    http = _FakeHttp([page1, page2])
    scraper = BestBuyScraper(api_key="fakekey", http_client=http, page_size=25, max_pages=20)
    records = list(scraper.iter_raw_records())
    assert len(records) == 30
