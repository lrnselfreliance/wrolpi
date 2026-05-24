/* Single-slide Calamares slideshow for WROLPi.
 *
 * Calamares treats the `slideshow:` key in branding.desc as required;
 * omitting it produces a FATAL error.  Until we have proper WROLPi
 * slideshow art, this minimal QML just shows our logo + a welcome line
 * during the install.
 *
 * Adapted from calamares-settings-debian (GPLv3+), which carries the
 * upstream Debian Live presentation.
 */

import QtQuick 2.0;
import calamares.slideshow 1.0;

Presentation
{
    id: presentation

    Timer {
        interval: 20000
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Image {
            id: background1
            source: "wrolpi-logo.png"
            width: 320; height: 320
            fillMode: Image.PreserveAspectFit
            anchors.centerIn: parent
        }
        Text {
            anchors.horizontalCenter: background1.horizontalCenter
            anchors.top: background1.bottom
            text: qsTr("Welcome to WROLPi.<br/>"+
                  "The rest of the installation is automated and should complete in a few minutes.")
            wrapMode: Text.WordWrap
            width: 600
            horizontalAlignment: Text.Center
        }
    }

}
