import pytest

from site_monitor.ssrf import UnsafeURLError, check_url_is_public, is_public_ip


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # private
        "172.17.0.2",  # private (default Docker bridge)
        "192.168.1.1",  # private
        "169.254.169.254",  # link-local: cloud metadata service
        "100.64.0.1",  # carrier-grade NAT
        "0.0.0.0",  # "this host"
        "224.0.0.1",  # multicast
        "::1",  # IPv6 loopback
        "fe80::1",  # IPv6 link-local
        "fd00::1",  # IPv6 unique local (private)
        "::ffff:127.0.0.1",  # IPv4-mapped IPv6 pointing to loopback
    ],
)
def test_non_public_ips_are_rejected(ip):
    assert is_public_ip(ip) is False


@pytest.mark.parametrize("ip", ["93.184.215.14", "8.8.8.8", "2606:4700:4700::1111"])
def test_public_ips_are_allowed(ip):
    assert is_public_ip(ip) is True


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://[::1]:8080/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5:9090/",
    ],
)
def test_ip_literal_urls_are_rejected(url):
    # IP literals are "resolved" locally, without any DNS query.
    with pytest.raises(UnsafeURLError):
        check_url_is_public(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://internal.example/",
        "https://metadata.example/",
        "https://mixed.example/",
        "https://does-not-resolve.example/",
    ],
)
def test_hostnames_are_judged_by_resolved_ips(fake_dns, url):
    with pytest.raises(UnsafeURLError):
        check_url_is_public(url)


def test_public_hostname_is_allowed(fake_dns):
    check_url_is_public("https://example.com/")  # must not raise
