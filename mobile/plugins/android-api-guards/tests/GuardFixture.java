import android.view.Window;
public final class GuardFixture {
  public static int run(Window window, int value) {
    window.setStatusBarColor(value);
    window.setNavigationBarColor(value);
    return window.getStatusBarColor();
  }
}
