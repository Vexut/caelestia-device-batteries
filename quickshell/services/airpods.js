.pragma library

// Which AirPods rings to show, from the scanner's reading.
//
//   reading: { left, right, case: 0..100 | null, charging: { left, right, case }, seen, ts }
//   (a charging pod is a pod that is in the case)
//
// Every combination:
//   both pods in the case   -> the case only
//   one pod in the case     -> the pod that is out, the pod in the case (dimmed), the case
//   both pods out           -> both pods, plus the case when its level is known
// A level the AirPods do not report (null) is simply left out, so a missing pod or an
// out-of-range case never shows as 0%.

var GLYPH_LEFT = 0x100C8E;
var GLYPH_RIGHT = 0x100C8D;
var GLYPH_CASE = 0x100E6B;

// How long a reading stays believable. While the AirPods are connected they advertise
// rarely, so a longer window is used; otherwise they are only shown while their lid is
// open, i.e. while advertisements are arriving.
var FRESH_CONNECTED = 300;
var FRESH_NEARBY = 30;

function isFresh(reading, now, connected) {
    if (!reading || typeof reading.seen !== "number")
        return false;
    return now - reading.seen < (connected ? FRESH_CONNECTED : FRESH_NEARBY);
}

function part(name, label, glyph, level, charging, dim) {
    // level null/undefined -> the ring is shown empty with "--" (the AirPods cannot report it)
    var known = level !== null && level !== undefined;
    return {
        name: name + " " + label,
        label: label,
        glyph: glyph,
        icon: glyph === GLYPH_CASE ? "earbuds_battery" : "earbuds",
        known: known,
        level: known ? level / 100 : -1,
        charging: charging === true,
        dim: dim === true,
        pair: false
    };
}

function entries(reading, name, caseLabel) {
    var out = [];
    if (!reading)
        return out;

    var charging = reading.charging || {};
    // Live ear detection says which pods are in the case; broadcasts only tell us a pod is
    // charging, which means the same thing.
    var inCase = reading.inCase;
    var leftIn = inCase ? inCase.left === true : charging.left === true;
    var rightIn = inCase ? inCase.right === true : charging.right === true;
    var has = function (v) { return v !== null && v !== undefined; };

    if (leftIn && rightIn) {
        // Both pods are in the case: one ring for the pair, showing their average.
        var lv = has(reading.left) ? reading.left : null;
        var rv = has(reading.right) ? reading.right : null;
        var avg = lv !== null && rv !== null ? Math.round((lv + rv) / 2) : (lv !== null ? lv : rv);
        var pair = part(name, "Pods", GLYPH_LEFT, avg, true, false);
        pair.pair = true;
        out.push(pair);
    } else {
        // A pod in the case is dimmed (its level is shown when known); one that is out is normal.
        // A pod that is out but unreported is simply missing, so it is left out.
        if (has(reading.left) || leftIn)
            out.push(part(name, "L", GLYPH_LEFT, reading.left, charging.left, leftIn));
        if (has(reading.right) || rightIn)
            out.push(part(name, "R", GLYPH_RIGHT, reading.right, charging.right, rightIn));
    }
    // The case is shown when its level is known, when a pod is in it, or when it is charging.
    if (has(reading.case) || leftIn || rightIn || charging.case === true)
        out.push(part(name, caseLabel || "Case", GLYPH_CASE, reading.case, charging.case, false));
    return out;
}
