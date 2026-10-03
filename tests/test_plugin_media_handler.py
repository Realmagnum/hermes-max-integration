
def test_extract_plugin_media_directives():
    from mixins.plugin_media_handler import extract_plugin_media_request
    caption, media_files, force_document = extract_plugin_media_request({
        "message": "Report MEDIA:/tmp/test.png [[as_document]]"
    })
    assert caption == "Report"
    assert media_files == [("/tmp/test.png", False)]
    assert force_document is True

def test_missing_media_path_rejected():
    from mixins.plugin_media_handler import extract_plugin_media_request
    _caption, media_files, _force_document = extract_plugin_media_request({
        "message": "Report MEDIA:/path/to/missing_non_existent.png"
    })
    # missing files are either filtered out or returned with error flag
    assert media_files == []
