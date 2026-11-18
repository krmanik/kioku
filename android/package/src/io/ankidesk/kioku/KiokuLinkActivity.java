package io.ankidesk.kioku;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;

/**
 * Receives kioku:// links (shared/python/kioku/urlscheme.py) and passes them
 * on to KiokuActivity, then closes without showing anything.
 *
 * Apps send links with FLAG_ACTIVITY_NEW_TASK; sent straight to the
 * singleTop KiokuActivity while Kioku was in the background, Android only
 * brought Kioku forward and dropped the link. CLEAR_TOP | SINGLE_TOP always
 * hands it to the running KiokuActivity (onNewIntent), or starts Kioku.
 *
 * The intent is the app icon's (MAIN, LAUNCHER) with the link as an extra:
 * when a link started Kioku, its task was keyed to the link, and tapping the
 * icon later could start a second KiokuActivity, which made Qt restart the
 * app. KiokuActivity turns the extra back into the VIEW intent Qt expects.
 */
public class KiokuLinkActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Intent link = getIntent();
        if (link != null && link.getData() != null) {
            Intent intent = new Intent(Intent.ACTION_MAIN)
                    .addCategory(Intent.CATEGORY_LAUNCHER)
                    .setClass(this, KiokuActivity.class)
                    .putExtra(KiokuActivity.EXTRA_LINK, link.getDataString())
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                            | Intent.FLAG_ACTIVITY_CLEAR_TOP
                            | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            startActivity(intent);
        }
        finish();
    }
}
