// Renders a two-tone SF Symbol on a white rounded square (sRGB PNG): the
// primary layer (the silhouette) in black, the secondary layer (the badge)
// in the requested color. Readable on light and dark notification backdrops.
//
// Usage:
//   swift tools/render-notif-icon.swift <symbol-name> <badge-color> <out-path>
//   badge-color ∈ {blue, gray, orange, green, red}  (orange = #f90)
//
// To regenerate the bundled notification icons:
//   swift tools/render-notif-icon.swift person.badge.key.fill   orange .swiftbar-aws-sso/notif-key.png
//   swift tools/render-notif-icon.swift person.badge.minus.fill orange .swiftbar-aws-sso/notif-minus.png
//   swift tools/render-notif-icon.swift person.badge.clock.fill orange .swiftbar-aws-sso/notif-clock.png

import AppKit
import Foundation

guard CommandLine.arguments.count >= 4 else { exit(1) }
let name     = CommandLine.arguments[1]
let colorArg = CommandLine.arguments[2]
let outPath  = CommandLine.arguments[3]

let badgeColor: NSColor
switch colorArg {
case "blue":   badgeColor = NSColor.systemBlue
case "gray":   badgeColor = NSColor.systemGray
case "orange": badgeColor = NSColor(srgbRed: 1.0, green: 0.6, blue: 0.0, alpha: 1.0)  // #f90
case "green":  badgeColor = NSColor.systemGreen
case "red":    badgeColor = NSColor.systemRed
default:       badgeColor = NSColor.systemBlue
}
let bg: NSColor = NSColor.white
let primaryColor: NSColor = NSColor.black

let canvasSize = NSSize(width: 512, height: 512)
let cornerRadius: CGFloat = 112
let symbolPointSize: CGFloat = 360

guard let base = NSImage(systemSymbolName: name, accessibilityDescription: nil) else { exit(2) }

let sizeCfg    = NSImage.SymbolConfiguration(pointSize: symbolPointSize, weight: .regular)
// Palette layer order for `person.badge.X`: [badge, silhouette].
let paletteCfg = NSImage.SymbolConfiguration(paletteColors: [badgeColor, primaryColor])
let combined   = sizeCfg.applying(paletteCfg)
let symbol: NSImage = base.withSymbolConfiguration(combined) ?? base

// Render into an sRGB-tagged 2x bitmap so explicit hex colors round-trip
// without being re-interpreted through Display P3.
let scale = 2
let pxW = Int(canvasSize.width)  * scale
let pxH = Int(canvasSize.height) * scale
guard let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: pxW, pixelsHigh: pxH,
    bitsPerSample: 8, samplesPerPixel: 4,
    hasAlpha: true, isPlanar: false,
    colorSpaceName: NSColorSpaceName.calibratedRGB,
    bytesPerRow: 0, bitsPerPixel: 0
) else { exit(5) }
rep.size = canvasSize
let srgbRep = rep.retagging(with: NSColorSpace.sRGB) ?? rep

guard let ctx = NSGraphicsContext(bitmapImageRep: srgbRep) else { exit(6) }
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = ctx

let rect = NSRect(origin: NSPoint.zero, size: canvasSize)
NSBezierPath(roundedRect: rect, xRadius: cornerRadius, yRadius: cornerRadius).addClip()
bg.setFill()
rect.fill()

let s = symbol.size
let symRect = NSRect(
    x: (canvasSize.width  - s.width)  / 2,
    y: (canvasSize.height - s.height) / 2,
    width: s.width,
    height: s.height
)
symbol.draw(in: symRect, from: NSRect.zero, operation: NSCompositingOperation.sourceOver, fraction: 1.0)

NSGraphicsContext.restoreGraphicsState()

guard let png = srgbRep.representation(using: NSBitmapImageRep.FileType.png, properties: [:]) else { exit(3) }
do { try png.write(to: URL(fileURLWithPath: outPath)) } catch { exit(4) }
