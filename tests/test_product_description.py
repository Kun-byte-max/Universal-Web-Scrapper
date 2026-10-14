import pytest
from bs4 import BeautifulSoup

from app.scraper.extractors import (
    is_valid_description,
    StrategyGeneralPage,
    StrategyStructuredMetadata,
    StrategyHTMLCards,
)
from app.scraper.parser import PageParser


# ==============================================================================
# 1. Copyright & Footer Rejection
# ==============================================================================

def test_copyright_rejection():
    """A footer copyright paragraph cannot become a product description."""
    html = """
    <html>
      <body>
        <main>
          <h1>Laboratory Centrifuge</h1>
          <img src="/img/centrifuge1.jpg" alt="Centrifuge 1" />
          <img src="/img/centrifuge2.jpg" alt="Centrifuge 2" />
          <footer class="site-footer">
            <p>© Copyright 2025. All Rights Reserved</p>
          </footer>
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    records = StrategyGeneralPage.extract(soup, "https://example.com/centrifuge")
    # Even if images exist, copyright must NOT qualify as valid description
    for rec in records:
        assert rec["description"] is None or "Copyright" not in rec["description"]
        assert "All Rights Reserved" not in (rec["description"] or "")


def test_is_valid_description_helper():
    """Verify is_valid_description rejects boilerplate variants while accepting prose."""
    # Rejections
    assert is_valid_description(None) is False
    assert is_valid_description("") is False
    assert is_valid_description("   ") is False
    assert is_valid_description("Too short") is False  # < 15 chars
    assert is_valid_description("© Copyright 2025. All Rights Reserved") is False
    assert is_valid_description("Copyright 2025 Med Freshe Private Limited") is False
    assert is_valid_description("All Rights Reserved.") is False
    assert is_valid_description("We use cookies to improve your experience. Accept all cookies.") is False
    assert is_valid_description("Cookie Policy and Settings") is False
    assert is_valid_description("Skip to main content") is False
    assert is_valid_description("Privacy Policy") is False
    assert is_valid_description("Terms of Service") is False

    # Acceptances
    valid_text = (
        "Historically, the term 'operating theatre' referred to a non-sterile, tiered theatre "
        "or amphitheater in which students and other spectators could watch surgeons perform surgery."
    )
    assert is_valid_description(valid_text) is True

    # Technical text containing 'terms' or 'privacy' in explanatory context
    tech_text = "The telemetry unit ensures patient privacy through end-to-end AES-256 data encryption."
    assert is_valid_description(tech_text) is True


# ==============================================================================
# 2. CMS Heading Prose Support (MedFreshe h4 pattern)
# ==============================================================================

def test_cms_heading_prose_selection():
    """Meaningful <h4>-wrapped prose is eligible as product description when <p> tags are absent."""
    html = """
    <html>
      <body>
        <main>
          <h1>Modular OT/ICU/ER – Med freshe Private Limited</h1>
          <section class="intro-section">
            <h3>AN INTRODUCTION</h3>
            <h4>Modular OT / ICU / Emergency Room / OT Integration (MOT)</h4>
            <h4>Historically, the term "operating theatre" referred to a non-sterile, tiered theatre or amphitheater in which students and other spectators could watch surgeons perform surgery. Contemporary operating rooms are devoid of a theatre setting, making the term "operating theatre" a misnomer.</h4>
            <h4>The most complex and challenging area of hospital construction is the operating department. Modular Operation Theatre (MOT) offers the advantage of speedy construction combined with design, future expansion and development in surgical technique whilst simultaneously providing a structure of the highest quality and standards.</h4>
          </section>
          <img src="/uploads/MOT-1.jpg" alt="Modular OT 1" />
          <img src="/uploads/MOT-2.jpg" alt="Modular OT 2" />
          <footer class="site-footer">
            <p>© Copyright 2025. All Rights Reserved</p>
          </footer>
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    records = StrategyGeneralPage.extract(soup, "https://medfreshe.com/modular-ot-icu-er/")
    assert len(records) == 1
    rec = records[0]
    assert rec["description"] is not None
    assert rec["description"].startswith('Historically, the term "operating theatre"')
    assert "Copyright" not in rec["description"]
    assert "All Rights Reserved" not in rec["description"]


# ==============================================================================
# 3. Body vs. Footer Priority
# ==============================================================================

def test_body_versus_footer():
    """Valid body prose takes precedence over any footer boilerplate."""
    html = """
    <html>
      <body>
        <main>
          <h1>Hospital Autoclave Sterilizer</h1>
          <p>High pressure steam sterilizer engineered for clinical surgical instruments and operating department hygiene.</p>
          <img src="/img/autoclave.jpg" alt="Autoclave" />
          <img src="/img/autoclave-chamber.jpg" alt="Chamber" />
          <footer>
            <p>© Copyright 2025. All Rights Reserved</p>
          </footer>
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    records = StrategyGeneralPage.extract(soup, "https://example.com/autoclave")
    assert len(records) == 1
    assert records[0]["description"] == (
        "High pressure steam sterilizer engineered for clinical surgical instruments and operating department hygiene."
    )


# ==============================================================================
# 4. Boilerplate-Only Page Produces No Description / No False Product
# ==============================================================================

def test_boilerplate_only_page():
    """Page with only copyright and cookie boilerplate produces no description and no false product."""
    html = """
    <html>
      <body>
        <main>
          <h1>Customer Portal</h1>
          <div class="cookie-banner">
            <p>We use cookies to enhance your experience. Accept all cookies to continue.</p>
          </div>
          <footer>
            <p>© Copyright 2025. All Rights Reserved</p>
          </footer>
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    records = StrategyGeneralPage.extract(soup, "https://example.com/portal")
    assert records == []


# ==============================================================================
# 5. Metadata Description Precedence
# ==============================================================================

def test_metadata_description_precedence():
    """Valid explicit JSON-LD metadata description takes precedence over on-page prose."""
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org/",
          "@type": "Product",
          "name": "Digital Patient Monitor",
          "description": "Clinical grade bedside patient vital signs monitor with 12.1 inch touchscreen.",
          "image": "/img/monitor.jpg",
          "offers": {
            "@type": "Offer",
            "price": "1450.00",
            "priceCurrency": "USD"
          }
        }
        </script>
      </head>
      <body>
        <main>
          <h1>Hospital Equipment Overview</h1>
          <p>Different body text that should not override the structured product description.</p>
        </main>
      </body>
    </html>
    """
    parser = PageParser(html, "https://example.com/monitor")
    records, strategy = parser.parse_records()
    assert "Strategy A" in strategy
    assert len(records) == 1
    assert records[0]["description"] == "Clinical grade bedside patient vital signs monitor with 12.1 inch touchscreen."


# ==============================================================================
# 6. HTML Card Compatibility
# ==============================================================================

def test_html_card_compatibility():
    """Existing card-based descriptions remain valid and reject footer boilerplate."""
    html = """
    <!DOCTYPE html>
    <html>
      <body>
        <div class="catalog-grid">
          <div class="product-card">
            <h3><a href="/prod/1">Surgical Lamp</a></h3>
            <img src="/img/lamp.jpg" alt="Lamp" />
            <div class="product-details">Ceiling mounted LED surgical illumination system with shadow reduction.</div>
            <span class="price">$3,200</span>
          </div>
          <div class="product-card">
            <h3><a href="/prod/2">Endoscopy Tower</a></h3>
            <img src="/img/endo.jpg" alt="Endo" />
            <div class="product-details">4K ultra high-definition video processor and xenon light source.</div>
            <span class="price">$8,500</span>
          </div>
        </div>
        <footer>
          <p>© Copyright 2025. All Rights Reserved</p>
        </footer>
      </body>
    </html>
    """
    parser = PageParser(html, "https://example.com/catalog")
    records, strategy = parser.parse_records()
    assert "Strategy B" in strategy
    assert len(records) == 2
    assert records[0]["description"] == "Ceiling mounted LED surgical illumination system with shadow reduction."
    assert records[1]["description"] == "4K ultra high-definition video processor and xenon light source."


# ==============================================================================
# 7. Product Association: Unrelated Page Prose Not Adopted By Cards
# ==============================================================================

def test_product_association_card_does_not_adopt_page_prose():
    """Product cards keep their scoped description and do not adopt unrelated page header prose."""
    html = """
    <!DOCTYPE html>
    <html>
      <body>
        <header>
          <div class="announcement">
            Welcome to our 2026 healthcare exhibition showcase where visitors can explore innovations.
          </div>
        </header>
        <div class="catalog-grid">
          <div class="product-card">
            <h3><a href="/p/1">Defibrillator Unit</a></h3>
            <img src="/img/defib.jpg" alt="Defibrillator" />
            <p class="summary">Biphasic automated external defibrillator with voice prompts.</p>
          </div>
          <div class="product-card">
            <h3><a href="/p/2">Infusion Pump</a></h3>
            <img src="/img/pump.jpg" alt="Pump" />
            <p class="summary">Volumetric syringe infusion pump with dose error reduction system.</p>
          </div>
        </div>
      </body>
    </html>
    """
    parser = PageParser(html, "https://example.com/pumps")
    records, strategy = parser.parse_records()
    assert len(records) == 2
    assert "Welcome to our 2026" not in records[0]["description"]
    assert records[0]["description"] == "Biphasic automated external defibrillator with voice prompts."


# ==============================================================================
# 8. Deterministic Multiple Paragraph Selection
# ==============================================================================

def test_multiple_paragraphs_deterministic_selection():
    """Selection follows deterministic rule: first valid descriptive block is chosen."""
    html = """
    <html>
      <body>
        <main>
          <h1>Surgical Pendant System</h1>
          <p>Primary overview: Ceiling articulated arm delivering medical gas and electrical utilities directly to surgeon.</p>
          <p>Secondary spec: Dual arm rotation up to 330 degrees with pneumatic friction brake mechanism.</p>
          <p>Third details: Compliant with ISO 11197 and HTM 02-01 health technical standards.</p>
          <img src="/img/pendant1.jpg" alt="Pendant 1" />
          <img src="/img/pendant2.jpg" alt="Pendant 2" />
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    records = StrategyGeneralPage.extract(soup, "https://example.com/pendant")
    assert len(records) == 1
    assert records[0]["description"] == (
        "Primary overview: Ceiling articulated arm delivering medical gas and electrical utilities directly to surgeon."
    )


# ==============================================================================
# 9. Unicode & Technical Text Preservation
# ==============================================================================

def test_unicode_and_technical_preservation():
    """Technical descriptions containing ±, °C, quotes, and em-dashes are preserved."""
    html = """
    <html>
      <body>
        <main>
          <h1>Cleanroom Environment Controller</h1>
          <p>Operating temperature range: -10°C to +50°C (±0.2°C accuracy); pressure gradient: 15 Pa ±2 Pa with “Ultra-Pur” filtration—certified under ISO 14644-1.</p>
          <img src="/img/cleanroom1.jpg" alt="Cleanroom 1" />
          <img src="/img/cleanroom2.jpg" alt="Cleanroom 2" />
        </main>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    records = StrategyGeneralPage.extract(soup, "https://example.com/controller")
    assert len(records) == 1
    desc = records[0]["description"]
    assert "±0.2°C" in desc
    assert "“Ultra-Pur”" in desc
    assert "filtration—certified" in desc


# ==============================================================================
# 10. Existing MedFreshe Fixture Baseline
# ==============================================================================

def test_medfreshe_fixture_extracts_intro_as_product_description():
    """The MedFreshe fixture now extracts the introductory text as the product description."""
    from tests.test_page_content import TARGET_MEDFRESHE_FIXTURE
    soup = BeautifulSoup(TARGET_MEDFRESHE_FIXTURE, "html.parser")
    records = StrategyGeneralPage.extract(soup, "https://medfreshe.com/modular-ot-icu-er/")
    assert len(records) == 1
    desc = records[0]["description"]
    assert desc is not None
    assert desc.startswith('Historically, the term "operating theatre"')
    assert "Copyright" not in desc


# ==============================================================================
# 11. Product Detection Stability
# ==============================================================================

def test_product_detection_footer_only_rejected_b2b_preserved():
    """Footer-only pages are rejected while genuine B2B product pages are preserved."""
    # 1. Non-product page with only footer copyright and images
    non_prod_html = """
    <html>
      <body>
        <main>
          <h1>Company Facilities Gallery</h1>
          <img src="/gallery1.jpg" alt="Facility 1" />
          <img src="/gallery2.jpg" alt="Facility 2" />
          <footer>
            <p>© Copyright 2025. All Rights Reserved</p>
          </footer>
        </main>
      </body>
    </html>
    """
    soup_np = BeautifulSoup(non_prod_html, "html.parser")
    # Because there is no valid description and no explicit e-commerce evidence, not detected as product
    records_np = StrategyGeneralPage.extract(soup_np, "https://example.com/gallery")
    assert records_np == []

    # 2. Legitimate B2B product with prose and images
    prod_html = """
    <html>
      <body>
        <main>
          <h1>Medical Gas Manifold System</h1>
          <p>Fully automatic digital changeover manifold supplying oxygen and nitrous oxide to operating theatres.</p>
          <img src="/manifold1.jpg" alt="Manifold 1" />
          <img src="/manifold2.jpg" alt="Manifold 2" />
          <footer>
            <p>© Copyright 2025. All Rights Reserved</p>
          </footer>
        </main>
      </body>
    </html>
    """
    soup_p = BeautifulSoup(prod_html, "html.parser")
    records_p = StrategyGeneralPage.extract(soup_p, "https://example.com/manifold")
    assert len(records_p) == 1
    assert records_p[0]["description"].startswith("Fully automatic digital changeover manifold")
