#!/usr/bin/env python

import StashInterface
import scrapeScenes
from flask import Flask, jsonify, request

tpdb = Flask(__name__)

@tpdb.route('/scan', methods = ['POST'])
def api_handler():
    data = request.form
    path = data.get('path', default=False)
    useFileMetadata = data.get('useFileMetadata', default=False)
    scanGeneratePreviews = data.get('scanGeneratePreviews', default=False)
    scanGenerateImagePreviews = data.get('scanGenerateImagePreviews', default=False)
    scanGenerateSprites = data.get('scanGenerateSprites', default=False)
    scrape = data.get('scrape', default=False)
    autotag = data.get('autotag', default=False)
    clean = data.get('clean', default=False)

    scan_options = ['-s']
    if useFileMetadata: scan_options.append('-ufm')
    if scanGeneratePreviews: scan_options.append('-sgp')
    if scanGenerateImagePreviews: scan_options.append('-sgi')
    if scanGenerateSprites: scan_options.append('-sgs')
    if path: scan_options.extend(['-p', path])
    StashInterface.main(scan_options)

    if scrape:
        scrapeScenes.main(['-no'])
    if autotag:
        StashInterface.main(['-at'])
    if clean:
        StashInterface.main(['-c'])

if __name__ == "__main__":
    port = 6969
    tpdb.run(host='0.0.0.0', port=port)