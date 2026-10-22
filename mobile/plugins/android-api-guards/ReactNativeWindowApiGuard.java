package lifemap.build;

import com.android.build.api.instrumentation.AsmClassVisitorFactory;
import com.android.build.api.instrumentation.ClassContext;
import com.android.build.api.instrumentation.ClassData;
import com.android.build.api.instrumentation.InstrumentationParameters;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.Label;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/** Keep the Android 24-34 implementation; Android 35+ owns transparent system bars. */
public abstract class ReactNativeWindowApiGuard
    implements AsmClassVisitorFactory<InstrumentationParameters.None> {
  @Override
  public boolean isInstrumentable(ClassData data) {
    String name = data.getClassName();
    return name.equals("com.facebook.react.views.view.WindowUtilKt")
        || name.equals("com.facebook.react.modules.statusbar.StatusBarModule")
        || name.startsWith("com.facebook.react.modules.statusbar.StatusBarModule$");
  }

  @Override
  public ClassVisitor createClassVisitor(ClassContext context, ClassVisitor next) {
    return new ClassVisitor(Opcodes.ASM9, next) {
      @Override
      public MethodVisitor visitMethod(int access, String name, String descriptor,
          String signature, String[] exceptions) {
        return new MethodVisitor(Opcodes.ASM9,
            super.visitMethod(access, name, descriptor, signature, exceptions)) {
          @Override
          public void visitMethodInsn(int opcode, String owner, String method,
              String desc, boolean isInterface) {
            boolean setter = (method.equals("setStatusBarColor")
                || method.equals("setNavigationBarColor")) && desc.equals("(I)V");
            boolean getter = method.equals("getStatusBarColor") && desc.equals("()I");
            if (opcode != Opcodes.INVOKEVIRTUAL || !owner.equals("android/view/Window")
                || !(setter || getter)) {
              super.visitMethodInsn(opcode, owner, method, desc, isInterface);
              return;
            }
            Label legacy = new Label();
            Label done = new Label();
            // The receiver and argument remain on the stack during the SDK check.
            super.visitFieldInsn(Opcodes.GETSTATIC, "android/os/Build$VERSION", "SDK_INT", "I");
            super.visitIntInsn(Opcodes.BIPUSH, 35);
            super.visitJumpInsn(Opcodes.IF_ICMPLT, legacy);
            if (setter) super.visitInsn(Opcodes.POP);
            super.visitInsn(Opcodes.POP);
            // Android 35+ has a transparent status bar, independent of the obsolete getter.
            if (getter) super.visitInsn(Opcodes.ICONST_0);
            super.visitJumpInsn(Opcodes.GOTO, done);
            super.visitLabel(legacy);
            super.visitMethodInsn(opcode, owner, method, desc, isInterface);
            super.visitLabel(done);
          }
        };
      }
    };
  }
}
