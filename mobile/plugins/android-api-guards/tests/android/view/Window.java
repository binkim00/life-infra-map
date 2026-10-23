package android.view;
public class Window {
  public int status = 17, navigation = 19, calls = 0;
  public void setStatusBarColor(int value) { status = value; calls++; }
  public void setNavigationBarColor(int value) { navigation = value; calls++; }
  public int getStatusBarColor() { calls++; return status; }
}
