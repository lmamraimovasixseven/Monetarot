from src.hashing import normalized_sha256


def test_normalized_sha256_is_identical_for_lf_and_crlf_files(tmp_path):
    lf_file = tmp_path / "lf.csv"
    crlf_file = tmp_path / "crlf.csv"
    lf_file.write_bytes(b"date,value\n2020-01,1\n2020-02,2\n")
    crlf_file.write_bytes(b"date,value\r\n2020-01,1\r\n2020-02,2\r\n")

    assert normalized_sha256(lf_file) == normalized_sha256(crlf_file)
