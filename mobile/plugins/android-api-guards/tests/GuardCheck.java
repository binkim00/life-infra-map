import android.os.Build;
import android.view.Window;
import com.android.build.api.instrumentation.InstrumentationContext;
import com.android.build.api.instrumentation.InstrumentationParameters;
import java.nio.file.Files;
import java.nio.file.Path;
import lifemap.build.ReactNativeWindowApiGuard;
import org.gradle.api.provider.Property;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;

/** Execute transformed bytecode, checking both sides of the Android 35 boundary. */
public final class GuardCheck {
  static final class Loader extends ClassLoader {
    Class<?> define(byte[] bytes) { return defineClass("GuardFixture", bytes, 0, bytes.length); }
  }
  public static void main(String[] args) throws Exception {
    ReactNativeWindowApiGuard guard = new ReactNativeWindowApiGuard() {
      @Override public Property<InstrumentationParameters.None> getParameters() { return null; }
      @Override public InstrumentationContext getInstrumentationContext() { return null; }
    };
    ClassWriter output = new ClassWriter(ClassWriter.COMPUTE_FRAMES | ClassWriter.COMPUTE_MAXS);
    new ClassReader(Files.readAllBytes(Path.of(args[0])))
        .accept(guard.createClassVisitor(null, output), ClassReader.EXPAND_FRAMES);
    Class<?> fixture = new Loader().define(output.toByteArray());
    for (int sdk : new int[] {24, 28, 34, 35, 36}) {
      Build.VERSION.SDK_INT = sdk;
      Window window = new Window();
      int result = (Integer) fixture.getMethod("run", Window.class, int.class).invoke(null, window, 42);
      boolean valid = sdk < 35
          ? window.status == 42 && window.navigation == 42 && window.calls == 3 && result == 42
          : window.status == 17 && window.navigation == 19 && window.calls == 0 && result == 0;
      if (!valid) throw new AssertionError("Window API regression at SDK " + sdk);
      System.out.println("SDK " + sdk + ": passed");
    }
  }
}
