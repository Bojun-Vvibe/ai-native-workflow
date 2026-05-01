public class Fq {
    public static Object roundtrip(byte[] xml) throws Exception {
        java.beans.XMLDecoder d = new java.beans.XMLDecoder(new java.io.ByteArrayInputStream(xml));
        Object out = d.readObject();
        d.close();
        return out;
    }
}
