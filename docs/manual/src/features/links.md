# kioku:// Links

> **Applies to:** iPhone and iPad, Android native

Other apps (Shortcuts, Tasker, dictionaries, a web page) can open a
`kioku://` link to add a note, sync or search. The actions and parameters
are the same as AnkiMobile's
([AnkiMobile's URL schemes](https://docs.ankiweb.net/ankimobile/url-schemes)),
under `kioku://` instead of `anki://`: to reuse an AnkiMobile shortcut,
change `anki://` to `kioku://`.

## Add a note

```
kioku://x-callback-url/addnote?type=Basic&deck=Default&fldFront=front%20text&fldBack=back%20text
```

| Parameter | Meaning |
| --- | --- |
| `type` | Note type name. Left out: the one the Add screen would pick. |
| `deck` | Deck name, subdecks with `::` (`Lang::Words`). Left out: the one the Add screen would pick. |
| `fld<Field>` | A field's text, as HTML (`fldFront` for the field "Front"; a line break is `<br>`). |
| `tags` | Tags, separated by spaces. |
| `dupes=1` | Add the note even if its first field matches another note's. |
| `profile` | Add only if this profile is open. |
| `x-success` | A link to open once the note is added, such as the app you came from. |

The note is added at once and Kioku shows "Added to …". If something is
wrong (no such deck, note type or field, an empty first field, a duplicate),
Kioku says what and adds nothing.

A field that holds only a link to an image or sound file, such as
`fldFront=https://example.com/cat.jpg`, is downloaded into the collection's
media and shown in the field. For a link without a file extension, add a
made-up one at the end: `…/getImage?id=12&fakePath=cat.jpg`.

Encode spaces and special characters (`%20` for a space; in Shortcuts, the
**URL Encode** action). A field link inside the link must be encoded too.

## Sync

```
kioku://x-callback-url/sync
```

Same as tapping **Sync**.

## Search

```
kioku://x-callback-url/search?query=deck:current%20is:due
```

Opens the Browse screen with this search.

## Not supported

AnkiMobile's `infoForAdding` (profile, deck and note type names for other
apps) isn't available.
