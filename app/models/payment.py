class Payment(Base):
    __tablename__ = "payments"

    id = mapped_column(primary_key=True)

    amount = mapped_column(Integer)
    payer_id = mapped_column(ForeignKey("users.id"))
    receiver_id = mapped_column(ForeignKey("users.id"))

    description = mapped_column(String)

    workflow_state_id = mapped_column(ForeignKey("workflow_states.id"))

    created_at = mapped_column(default=datetime.utcnow)

    workflow_state = relationship("WorkflowState")
