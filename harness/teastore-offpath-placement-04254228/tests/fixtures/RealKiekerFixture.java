import java.nio.ByteBuffer;
import java.util.Base64;
import java.util.List;
import kieker.common.configuration.Configuration;
import kieker.common.record.controlflow.OperationExecutionRecord;
import kieker.monitoring.writer.serializer.BinarySerializer;
import tools.descartes.teastore.kieker.probes.records.OperationExecutionWithParametersRecord;

public final class RealKiekerFixture {
  public static void main(String[] args) {
    BinarySerializer serializer = new BinarySerializer(new Configuration());
    serializer.onInitialization();
    OperationExecutionRecord record = new OperationExecutionRecord(
        "public void tools.descartes.teastore.auth.A.login()",
        "sess", 123L, 1000L, 2000L, "auth-host", 0, 0);
    ByteBuffer buffer = ByteBuffer.allocate(65536);
    OperationExecutionWithParametersRecord withParameters =
        new OperationExecutionWithParametersRecord(
            "public boolean tools.descartes.teastore.auth.A.login(java.lang.String)",
            "sess", 123L, 1100L, 1900L, "auth-host", 1, 1,
            new String[] {"java.lang.String"}, new String[] {"secret-redacted"},
            "boolean", "true");
    int count = serializer.serializeRecords(List.of(record, withParameters), buffer);
    buffer.flip();
    byte[] bytes = new byte[buffer.remaining()];
    buffer.get(bytes);
    System.out.println("count=" + count + " bytes=" + bytes.length);
    System.out.println(Base64.getEncoder().encodeToString(bytes));
  }
}
