# sample_reading_media

Test sample ebooks, etc. Formats:

  * test_book.md
  * test_book_md.md
  * test_book_txt.txt
  * test_book_txt_crlf_win.txt
  * test_book_txt_lf_unix.txt
  * test_book_html.html
  * test_book_odt.odt
  * test_book_docx.docx
  * test_book_pdf.pdf
  * test_book_fb2.fb2
  * test_book_epub.epub
  * test_book_md_zip.zip
  * test_book_txt_zip.zip
  * test_book_html_zip.zip
  * test_book_fb2_zip.zip
  * test_book_rtf.rtf
  * test_book_rtf_zip.zip

All the above sample books are generated from [test_book.md](./test_book.md).

  * source_test_book_fb2.fb2
  * source_test_book_fb2_zip.fbz
  * source_test_book_fb2_dot_zip.fb2.zip
  * test_book_epub_more_detail.epub
  * test_book_pdf_more_detail.pdf

LGPL license, so feel free to use in/with your projects. If you modify them, share your changes.

Test sample comics, Formats:

  * bobby_make_believe_sample.cb7
  * bobby_make_believe_sample.cbt
  * bobby_make_believe_sample.cbz
  * bobby_make_believe_sample.cbr
  * bobby_make_believe_sample_dir.cb7
  * bobby_make_believe_sample_dir.cbt
  * bobby_make_believe_sample_dir.cbz


For Comic book also sample, see https://www.contrapositivediary.com/?p=1197
(e.g. http://www.copperwood.com/pub/Elf%20Receiver%20Radio-Craft%20August%201936.cbz)

Images in images/bobby_make_believe/ are in the Public Domain and are the first 4 four pages of "Bobby Make-Believe (1915)" from https://comicbookplus.com/?dlid=26481

## Build setup

    # Assuming Debian based
    sudo apt install pandoc zip
    sudo apt install wget
    sudo apt install p7zip-full
    sudo apt install rar

Issue build:

    ./build.sh

## TODO

  * add images (e.g. to html, embedded and linked, epub, new md file with images etc.)
  * fb2 with title page/images
  * hand crafted html (e.g. include metadata)
  * mobi
  * prc/pdb?
  * azw
  * azw3
  * add comics
      * CBR
      * epub with images only
  * metadata for formats that support it
      * mobi
      * azw/azw3
      * Comic metadata; zip comment or a ComicInfo.xml - see
          * https://github.com/dickloraine/EmbedComicMetadata
          * https://github.com/comictagger/comictagger
          * https://code.google.com/archive/p/comicbookinfo/ (wiki)
          * https://wiki.mobileread.com/wiki/CBR_and_CBZ#Metadata

