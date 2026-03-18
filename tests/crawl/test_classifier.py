from src.crawl.classifier import PageClassifier


def test_classifier_maps_common_smb_pages():
    classifier = PageClassifier()

    assert classifier.classify("https://example.com/") == "homepage"
    assert classifier.classify("https://example.com/services", anchor_text="Services") == "service"
    assert classifier.classify("https://example.com/locations/echo-park") == "location"
    assert classifier.classify("https://example.com/faq") == "faq"
    assert classifier.classify("https://example.com/about-us") == "about"
    assert classifier.classify("https://example.com/contact") == "contact"
    assert classifier.classify("https://example.com/testimonials") == "testimonial"
    assert classifier.classify("https://example.com/book-now", anchor_text="Book Now") == "pricing_booking"


def test_classifier_ignores_junk_urls():
    classifier = PageClassifier()

    assert classifier.is_relevant("https://example.com/services")
    assert not classifier.is_relevant("https://example.com/privacy-policy")
    assert not classifier.is_relevant("https://example.com/terms")
    assert not classifier.is_relevant("https://example.com/wp-content/uploads/menu.pdf")

